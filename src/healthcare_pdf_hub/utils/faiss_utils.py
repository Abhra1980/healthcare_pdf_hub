# Code to create/store the index for FAISS and retreive the relevant documents

# langchain vectorstores documentation: https://python.langchain.com/docs/modules/data_connection/vectorstores/integrations/faiss
from typing import List
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import HuggingFaceEmbeddings

def create_faiss_index(texts: List[str]) -> FAISS:
    # Use a lighter model to reduce load + avoid big downloads
    model_name = "sentence-transformers/all-MiniLM-L6-v2"  # lighter than all-mpnet-base-v2
    embeddings = HuggingFaceEmbeddings(model_name=model_name)
    return FAISS.from_texts(texts, embeddings)

def retrive_relevant_docs(vectorstore: FAISS, query: str, k: int = 4):
    return vectorstore.similarity_search(query, k=k)
