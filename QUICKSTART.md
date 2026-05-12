# Quick Start Guide

## 🚀 Launch in 3 Steps

### Step 1: Configure API Key
```bash
cp .env.example .env
# Edit .env and add your OpenAI API key (https://platform.openai.com/account/api-keys)
```

### Step 2: Choose Deployment Method

#### Option A: Local Development (Recommended)
```bash
# Terminal 1: Start Qdrant vector database
docker run -p 6333:6333 qdrant/qdrant:v1.7.0

# Terminal 2: Start API with reload
python -m uvicorn src.main:app --reload
# → API at http://localhost:8000
# → Docs at http://localhost:8000/docs
```

#### Option B: Docker Compose (Production)
```bash
docker-compose up --build
# → API at http://localhost:8000
# → Qdrant at http://localhost:6333
```

### Step 3: Test the System

**Upload a document** (in your browser or with curl):
```bash
curl -X POST http://localhost:8000/api/documents/upload \
  -F "file=@data/sample_supply_chain_forecast.txt"
```

**Query the RAG system**:
```bash
curl -X POST http://localhost:8000/api/query/ \
  -H "Content-Type: application/json" \
  -d '{"query": "What is the Q3 demand forecast?", "top_k": 5}'
```

**Check health**:
```bash
curl http://localhost:8000/health
```

---

## 📚 Documentation
- **README.md** - User-facing guide with API examples
- **ARCHITECTURE.md** - Deep dive into design and tech stack
- **Swagger UI** - http://localhost:8000/docs (interactive testing)

---

## 🧪 Run Tests
```bash
# All tests
pytest tests/ -v

# With coverage
pytest tests/ --cov=src
```

---

## 🎯 Next Steps
1. Upload your supply chain documents
2. Try different queries to test retrieval quality
3. Customize `RAGPipeline` for your specific document types
4. Add metadata filtering (supplier, date, category)
5. Deploy to Azure or your cloud platform

---

**Need help?** See README.md or ARCHITECTURE.md for detailed information.
