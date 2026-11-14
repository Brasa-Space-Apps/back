from fastapi import FastAPI

app = FastAPI(title="Brasa")

@app.get("/")
def read_root():
    return {"status": "online", "mensagem": "API rodando com FastAPI!"}