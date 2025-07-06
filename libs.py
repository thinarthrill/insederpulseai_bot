import os
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings
from langchain.text_splitter import CharacterTextSplitter
import re
import requests
from openai import AsyncOpenAI
from dotenv import load_dotenv
import os


load_dotenv()
os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY")


# функция для загрузки документа Docx по ссылке из гугл драйв
def download_google_doc(url: str) -> str:
    # Извлекаем ID документа из URL
    match_ = re.search(r'/document/d/([a-zA-Z0-9-_]+)', url)
    if not match_:
        raise ValueError("Invalid Google Docs URL")
    doc_id = match_.group(1)
    download_url = f'https://docs.google.com/document/d/{
        doc_id}/export?format=txt'
    response = requests.get(download_url, stream=True)
    if response.status_code != 200:
        raise RuntimeError("Failed to download the document")
    return response.text


# (CharacterTextSplitter) Формируем чанки из текста по количеству символов
def split_text(text: str,
               chunk_size=3000,     # Ограничение к-ва символов в чанке
               chunk_overlap=300):  # к-во символов перекрытия в чанке
    # Создаем экземпляр CharacterTextSplitter с заданными парамаетрами
    splitter = CharacterTextSplitter(chunk_size=chunk_size,
                                     chunk_overlap=chunk_overlap,
                                     separator="\n")
    return splitter.split_text(text)  # список текстовых чанков


# Создание и сохранение индексной базы
def create_db_index(url, path='', index_name='db_index'):
    text = download_google_doc(url)
    chunks = split_text(text)
    # Создаем индексную базу с использованием FAISS
    db_index = FAISS.from_texts(chunks, OpenAIEmbeddings())
    # Сохраняем нидексную базу
    db_index.save_local(folder_path=path, index_name=index_name)


# Загрузка ранее сохраненной индексной базы
def load_db_index(index_name='db_index', path=''):
    return FAISS.load_local(
        folder_path=path,
        allow_dangerous_deserialization=True,
        embeddings=OpenAIEmbeddings(),
        index_name=index_name)


# Запрос к OpenAI с выбором чанков из векторной базы
async def answer_db_index(system,            # системный промпт
                          user_query,        # запрос пользователя
                          db_index,          # индексная база знаний из текстов
                          k=3,               # количество подтягиваемых чанков из базы
                          model='gpt-4o-mini',
                          temp=0.1):
    docs = db_index.similarity_search(user_query, k=k)
    message_content = re.sub(r'\n{2}', ' ', '\n '.join(
        [f'\nОтрывок № {i+1}:\n' + doc.page_content for i, doc in enumerate(docs)]))
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content":
         f"База знаний по ТЕХНИЧЕСКОМУ РЕГЛАМЕНТУ ТАМОЖЕННОГО СОЮЗА 'О БЕЗОПАСНОСТИ ЖЕЛЕЗНОДОРОЖНОГО ПОДВИЖНОГО СОСТАВА' \
         с информацией для ответа пользователю: \n{message_content} \n\n{user_query}."}]
    response = await AsyncOpenAI().chat.completions.create(
        model=model,
        messages=messages,
        temperature=temp)
    return response.choices[0].message.content
