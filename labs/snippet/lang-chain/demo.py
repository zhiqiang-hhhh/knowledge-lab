from langchain_core.documents import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import ApacheDoris
from langchain_community.vectorstores.apache_doris import ApacheDorisSettings
from langchain_community.vectorstores.apache_doris import DEBUG as DorisDebug
from langchain_community.vectorstores import FAISS
from langchain_openai import ChatOpenAI
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_core.prompts import ChatPromptTemplate
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain.chains import create_retrieval_chain
import os

# 1) Toy knowledge base
docs = [
    Document(page_content="The basilisk is a mythical creature said to defeat foes with a single glance."),
    Document(page_content="Basilisks are often described as reptilian; some legends claim they avoid the scent of weasels."),
    Document(page_content="Best practices for caring for basil plants: give them sunlight and prune regularly."),
    Document(page_content="In medieval lore, travelers carried mirrors to reflect a basilisk's gaze.")
]

# 2) Chunk the docs
splitter = RecursiveCharacterTextSplitter(chunk_size=250, chunk_overlap=40)
chunks = splitter.split_documents(docs)

# 3) Embed + index
emb = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")


DorisDebug = True
# ## TODO: Need a create database stmt.
settings = ApacheDorisSettings(
    host="127.0.0.1",
    port=6937,  # Apache Doris default MySQL port
    username="root",
    password="",
    database="vector_test",
)

vectordb = ApacheDoris.from_documents(chunks, emb, config=settings)
vectordb = FAISS.from_documents(chunks, emb)
retriever = vectordb.as_retriever(search_kwargs={"k": 3})

# 4) Prompt + LLM
prompt = ChatPromptTemplate.from_messages([
    ("system",
     "You answer strictly using the provided context. "
     "If the answer is not in the context, say you don't know.\n\n"
     "Context:\n{context}"),
    ("human", "{input}")
])

llm = ChatOpenAI(
    model=os.getenv("OPENAI_MODEL", "deepseek-ai/DeepSeek-R1-0528-Qwen3-8B"),
    base_url=os.getenv("OPENAI_BASE_URL", "https://api.siliconflow.cn/v1"),
    api_key=os.getenv("OPENAI_API_KEY", "sk-arpnxpvljxxoolbtncnhubxkwpndosileymeamorsiefofsw"),
    temperature=0,
)

# 5) Build RAG chain: (retriever) -> (stuff docs into prompt) -> (LLM)
doc_chain = create_stuff_documents_chain(llm, prompt)
rag_chain = create_retrieval_chain(retriever, doc_chain)

# 6) Ask something
question = "What does the basilisk eat, according to these notes?"
result = rag_chain.invoke({"input": question})

print("\nQUESTION:", question)
print("\nANSWER:", result["answer"])
print("\n--- Top retrieved chunks ---")
for i, d in enumerate(result["context"], 1):
    print(f"[{i}] {d.page_content[:200]}...")
