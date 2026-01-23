from API.database import engine
from API.models import Base

print("Criando tabelas...")
Base.metadata.create_all(bind=engine)
print("Tabelas criadas com sucesso 🚀")
