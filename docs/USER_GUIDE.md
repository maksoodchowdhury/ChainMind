# SupplyChain RAG Assistant — User Guide

> **Who is this guide for?** Anyone who needs to ask questions about supply chain documents — demand plans, supplier info, inventory policies, risk reports — without needing to read every file manually or write a single line of code.

---

## Table of Contents

1. [What Is This Tool?](#1-what-is-this-tool)
2. [What Can It Do For You?](#2-what-can-it-do-for-you)
3. [Before You Start](#3-before-you-start)
4. [How to Start the Application](#4-how-to-start-the-application)
5. [How to Upload Your Documents](#5-how-to-upload-your-documents)
6. [How to Ask Questions](#6-how-to-ask-questions)
7. [How to Use the Interactive Interface](#7-how-to-use-the-interactive-interface)
8. [Filtering Results by Document Type](#8-filtering-results-by-document-type)
9. [Running the Demo](#9-running-the-demo)
10. [Frequently Asked Questions](#10-frequently-asked-questions)
11. [Glossary](#11-glossary)
12. [How to Enhance This Tool With AI](#12-how-to-enhance-this-tool-with-ai)

---

## 1. What Is This Tool?

The **SupplyChain RAG Assistant** is a smart search and question-answering system built specifically for supply chain documents. Think of it as a very knowledgeable colleague who has read every document you have uploaded — and can answer your questions in plain English, instantly.

**Example:** Instead of manually searching through a 50-page demand forecast report, you can ask:

> *"Which product categories have the highest Q1 2025 demand growth?"*

…and get a focused, accurate answer in seconds.

**RAG** stands for *Retrieval-Augmented Generation*. In plain terms: the system first *retrieves* the most relevant passages from your documents, then uses an AI language model to *generate* a clear answer based only on what it retrieved. It does not make things up — it stays grounded in your documents.

---

## 2. What Can It Do For You?

| What you want to know | Example question |
|---|---|
| Demand & forecasts | "What is the forecasted demand for Industrial Automation in Q1?" |
| Supplier performance | "Which suppliers have single-source risk?" |
| Inventory rules | "How is safety stock calculated?" |
| Risk management | "What are the critical supply chain risks and mitigation plans?" |
| Cross-document reasoning | "Mitsuya is single-source — what is the demand for their products?" |
| Policy lookups | "What happens when inventory hasn't moved in 6 months?" |
| Trend analysis | "Which regions show the strongest demand growth?" |

You can ask questions in natural language — no special syntax required.

---

## 3. Before You Start

### What you need

- The API must be running. Ask your IT/engineering team to start it, or follow the README to run it yourself.
- Your documents (PDF, Word `.docx`, plain text `.txt`, CSV, Excel `.xlsx`, Markdown `.md`) ready to upload.
- A web browser (Chrome, Firefox, Edge, Safari — all work).

### The two ways to use it

| Method | Best for |
|---|---|
| **Interactive web UI** (Swagger) | Exploring, one-off questions, testing |
| **Demo script** | Presentations, showing the full workflow end-to-end |

### Checking the API is running
Open your browser and go to: `http://localhost:8000/health`

You should see:
```json
{"status": "healthy", "service": "SupplyChain RAG Assistant", "version": "0.2.0"}
```

If you see an error, the API is not running yet.

---

## 4. How to Start the Application

### Option A: Using Docker (Recommended, simplest)

**What you need:**
- Docker and Docker Compose installed
- A terminal window
- The project folder open

**Step 1 — Navigate to the project folder**

```bash
cd /path/to/SupplyChain-RAG-Assistant
```

**Step 2 — Start the application with one command**

```bash
docker-compose up --build
```
This will:
- Build the FastAPI application container
- Start Qdrant vector database
- Start the API on `http://localhost:8000`
- Display logs in real-time

**You will see output like:**
```
api_1     | INFO:     Application startup complete
api_1     | INFO:     Uvicorn running on http://0.0.0.0:8000
```

**Step 3 — Open the interface**

In your browser, go to:
- **Web UI (recommended):** `http://localhost:8000/ui`
- **Swagger Docs:** `http://localhost:8000/docs`

**To stop the application:**

Press `Ctrl+C` in the terminal, or in another terminal run:
```bash
docker-compose down
```

---

### Option B: Manual setup (Advanced)

If you prefer not to use Docker, you can run the components separately.

**Step 1 — Start Qdrant (in Terminal 1)**

```bash
docker run -p 6333:6333 qdrant/qdrant
```

**Step 2 — Activate Python environment and start the API (in Terminal 2)**

```bash
cd /path/to/SupplyChain-RAG-Assistant
source .venv/bin/activate          # On Windows: .venv\Scripts\activate
pip install -r requirements.txt    # If dependencies not installed yet
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

You should see:
```
INFO:     Uvicorn running on http://0.0.0.0:8000
```

**Step 3 — Open the interface (same as Option A)**

---

### Option C: Run the Interactive Demo (Quickest way to see it working)

If you have the API already running, you can see the system in action with pre-built demo documents and questions.

**In Terminal 3 (while the API is running):**

```bash
cd /path/to/SupplyChain-RAG-Assistant
source .venv/bin/activate
python demo/run_demo.py --host http://localhost:8000
```

This will:
1. Check the API is healthy
2. Upload 4 sample supply chain documents
3. Run 10 real-world queries
4. Show answers with sources

**Expected output:**
```
✓ API Health: Healthy
✓ Document 1/4 uploaded: demand_forecast_q1_2025.txt
...
✓ Query 1: What are the critical supply chain risks in Q1 2025?
✓ Query 2: Which suppliers have single-source risk exposure?
...
Demo Complete
```

---

## 5. How to Upload Your Documents

### Using the Web UI (Easiest)

Go to: **`http://localhost:8000/ui`**

You will see a clean interface with three sections:
1. **Upload Documents** — drag and drop or select files
2. **Query the Knowledge Base** — ask questions and see answers with source citations
3. **Indexed Documents** — view all uploaded files and storage stats

### Step-by-step upload

**Step 1** — In the "Upload Documents" section, click **"Choose File"** and select your document

**Step 2** — (Optional) Fill in the metadata fields:
- **Supplier:** Who created or provided this document (e.g., `acme-planning`)
- **Document Type:** What kind of document (e.g., `demand_plan`, `inventory_policy`)
- **Date Period:** The time period it covers (e.g., `Q1-2025`)

**Step 3** — Click **"Upload & Index"**

You will see:
- A success message with the job ID
- The document appears in the "Ingestion Jobs" list
- Status updates from `PENDING` to `COMPLETED`

**Step 4** — Once complete, the document appears in the "Indexed Documents" section below

---

### Using the Swagger Docs (Advanced)

Alternatively, you can use the technical API interface at: **`http://localhost:8000/docs`**

Scroll down to **`POST /api/documents/upload`** and click **"Try it out"**.

**Fill in the form:**

| Field | What to enter | Example |
|---|---|---|
| `file` | Click "Choose File" and pick your document | `demand_plan_q1.pdf` |
| `supplier` | Who created or supplied this document | `acme-planning` |
| `doc_type` | What kind of document it is | `demand_plan` |
| `date_period` | The time period it covers | `Q1-2025` |

> **Tip:** The `doc_type` and `date_period` fields are optional but make your searches much more precise. Use consistent values so you can filter later (e.g., always use `risk_assessment` not sometimes `risk` or `risks`).

Click **"Execute"** to upload.

The system will return a job ID. The document is now being processed in the background (read, split into chunks, indexed for search). This usually takes **5–30 seconds** depending on document size.

**Check the status:**

In the Swagger UI, go to **`GET /api/documents/status/{job_id}`**, enter your `job_id`, and click **Execute**.

You will see:
- `"status": "COMPLETED"` when finished
- `"chunks_indexed": 42` showing how many searchable sections were created
- Or `"status": "FAILED"` with an error message if something went wrong

### What file types are supported?

| Format | Notes |
|---|---|
| `.txt` | Plain text, works great |
| `.pdf` | Supported (text is extracted) |
| `.md` | Markdown files |
| `.csv` | Each row group becomes a searchable chunk |
| `.xlsx` / `.xls` | Excel — each sheet is processed separately |

> **Note:** Image-only PDFs (scanned documents with no selectable text) are not supported. The text must be extractable.

---

## 6. How to Ask Questions

### Using the web UI

1. Go to `http://localhost:8000/ui`
2. Scroll to the "Query the Knowledge Base" section
3. Enter your question in the text box
4. (Optional) Adjust "Top K" (number of sources) and add filters
5. Click **"Ask Question"**

You will see:
- The answer in the "Answer" section
- Relevant source documents below it with relevance scores
- Query metrics showing response time and source information

### Tips for better answers

| Tip | Example |
|---|---|
| Be specific | "What is the safety stock formula for Consumer Electronics?" instead of "safety stock?" |
| Add context | "According to the Q1 2025 risk report, what is the mitigation for RISK-001?" |
| Ask comparative questions | "Compare the on-time delivery rates of our top three suppliers" |
| Ask for numbers | "What is the forecasted demand in units for Q1 2025 Industrial Automation?" |
| Ask for recommendations | "Which supplier should I use for aluminium if Novelis is unavailable?" |

### The `top_k` parameter

This controls how many document chunks the system retrieves before generating an answer. The default is 5.

- Use **3–4** for focused, specific factual questions
- Use **5–8** for broad analytical questions that span multiple documents

### Using the Swagger Docs (Advanced)

Alternatively, go to `http://localhost:8000/docs` and find **`POST /api/query/`**. Click "Try it out" and replace the example JSON with your question:

```json
{
  "query": "What are the critical supply chain risks in Q1 2025?",
  "top_k": 5
}
```

---

## 7. How to Use the Interactive Interface

The web interface at `http://localhost:8000/ui` is organized into three main sections:

| Section | What it does |
|---|---|
| **Upload Documents** | Add new documents with optional metadata labels |
| **Query the Knowledge Base** | Ask questions and view answers with source citations and relevance scores |
| **Indexed Documents** | View all uploaded files, storage statistics, and charts showing file types and sizes |

The interface also shows:
- **System Status** — Whether the API and Qdrant database are healthy
- **Ingestion Jobs** — Progress of document uploads and indexing
- **Query Metrics** — Response time, source relevance scores, and source count
- **Charts** — Visual breakdown of your document library by type and size

---

## 7. Filtering Results by Document Type

When you have many documents indexed, you can tell the system to only search within specific documents. This is called **metadata filtering**.

In the query form, add a `filters` object:

```json
{
  "query": "What is the reorder point formula?",
  "top_k": 4,
  "filters": {
    "doc_type": "inventory_policy"
  }
}
```

Available filter fields:

## 8. Filtering Results by Document Type

When you have many documents indexed, you can tell the system to only search within specific documents. This is called **metadata filtering**.

### Using the web UI

In the "Query the Knowledge Base" section, use the optional filter fields:
- **Filter: Supplier** — Narrow to documents from a specific supplier
- **Filter: Document Type** — Narrow to specific document types
- **Filter: Date Period** — Narrow to a specific time period

Just type in the filter you want and click **"Ask Question"**.

### Using the Swagger Docs

In the query form (at `http://localhost:8000/docs`), add a `filters` object:

You can combine multiple filters. Only documents matching **all** filters will be searched.

---

## 9. Running the Demo

The demo script uploads four pre-built synthetic documents and runs 10 interesting queries automatically. It is ideal for presentations.

### Prerequisites

1. Python installed on your machine
2. API is running (`uvicorn src.main:app --reload`)
3. Qdrant is running (`docker run -p 6333:6333 qdrant/qdrant`)

### Running the demo

Open a terminal in the project folder and run:

```bash
python demo/run_demo.py
```

The script will:
1. Check the API is healthy
2. Upload all 4 demo documents (demand forecast, supplier directory, inventory policy, risk assessment)
3. Wait for indexing to complete
4. Run 10 questions across all document types
5. Display formatted answers with source attribution

If you have already uploaded the documents and don't want to re-upload:

```bash
python demo/run_demo.py --skip-upload
```

---

## 10. Frequently Asked Questions

**Q: The system says "No relevant documents found". What's wrong?**

A: Either (a) no documents have been uploaded yet, or (b) your question uses terminology that doesn't match your documents. Try rephrasing, or use broader terms.

**Q: The answer is wrong or made up.**

A: The system only uses information from your uploaded documents. If the answer seems wrong, check the `sources` field — it shows exactly which document passages were used. The underlying question may need rewording, or the correct document may not have been uploaded yet.

**Q: Can I upload the same document twice?**

A: The system automatically detects duplicate files (using a content fingerprint) and skips re-indexing. You will still get a job ID, but the status will show it was already indexed.

**Q: How many documents can I upload?**

A: There is no hard limit in the software. Performance depends on your Qdrant setup. Thousands of documents work well.

**Q: Does it work offline / without internet?**

A: By default, it uses OpenAI's API (requires internet). If your team has set up a local embedding model, it can work offline — ask your technical team.

**Q: Can I delete indexed documents?**

A: Currently, deletion requires re-initialising the vector database. Ask your technical team to add a delete endpoint if needed (see the Enhancement section below).

**Q: Is my data sent to OpenAI?**

A: The document text is sent to OpenAI's API to generate embeddings and answers. If your documents are confidential, discuss with your IT/security team whether to use a self-hosted model instead.

---

## 11. Glossary

| Term | Plain-English meaning |
|---|---|
| **RAG** | "Retrieval-Augmented Generation" — the technique of finding relevant passages first, then generating an answer from them |
| **Embedding** | A mathematical representation of text that captures its meaning, used for searching |
| **Vector search** | Searching by meaning, not just by exact words |
| **Chunk** | A small section of a document (typically 1–2 paragraphs) that is indexed individually |
| **Index** | The searchable database of all uploaded document chunks |
| **Qdrant** | The vector database that stores and searches the document chunks |
| **LLM** | "Large Language Model" — the AI (e.g., GPT-4) that generates the final answer |
| **Metadata** | Extra labels attached to a document (supplier, doc_type, date_period) to enable filtering |
| **Top-K** | How many chunks to retrieve before generating an answer |
| **Job ID** | A unique identifier for a background indexing task |
| **Streaming** | Delivering the answer word-by-word as it is generated (like ChatGPT typing in real time) |

---

## 12. How to Enhance This Tool With AI

You can ask an AI assistant (GitHub Copilot, ChatGPT, Claude) to help you extend this system. Here are ready-to-use prompts:

### Adding a new document type

> "I have a new document type called `purchase_order`. I want the SupplyChain RAG Assistant to support filtering by `po_number` and `vendor_code` in addition to the existing metadata fields. Show me what changes are needed in `src/api_documents.py` and `src/api_query.py`."

### Adding a delete endpoint

> "The SupplyChain RAG Assistant (FastAPI + Qdrant + LlamaIndex) doesn't have a delete document endpoint. Add `DELETE /api/documents/{document_id}` that removes a document and all its chunks from the Qdrant collection. The file `src/api_documents.py` contains the existing document endpoints."

### Improving answer formatting

> "The query endpoint in `src/api_query.py` returns a plain text answer. I want to also return the answer as structured JSON with fields: `summary` (2-sentence summary), `key_facts` (bullet list of specific numbers/dates found), and `confidence` (low/medium/high). Show me how to modify the response model and prompt."

### Adding a Slack or Teams notification

> "I want the SupplyChain RAG Assistant to send a Slack notification whenever a document finishes indexing. The indexing happens in `src/ingestion_worker.py`. Show me how to add a Slack webhook call at the end of a successful ingestion job."

### Deploying to Azure

> "I want to deploy the SupplyChain RAG Assistant (FastAPI app in Docker) to Azure Container Apps. The project has a `docker-compose.yml`. Generate the Azure Bicep templates and GitHub Actions workflow to deploy it to Azure."
