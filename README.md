# Clara AI - Intern Automation Assignment

This repository contains the zero-cost automation pipeline for converting raw demo and onboarding transcripts into structured operational rules and version-controlled Retell Agent Configurations.

## 🏗 Architecture and Data Flow

This pipeline uses **n8n** as the orchestrator running locally via Docker. To meet the strict "zero spend" constraint without sacrificing reliability, the extraction logic is handled by a local Python script utilizing rule-based NLP extraction rather than relying on paid external LLM APIs.

**Data Flow:**
1. **Ingestion:** Text transcripts of demo and onboarding calls are placed in the `transcripts/` directory. (Note: Audio recordings can be transcribed using a free tool like local Whisper and placed here).
2. **Orchestration:** The user triggers the n8n workflow, which executes a batch processing script (`run_batch.sh`).
3. **Demo Pipeline (v1):** The python script (`process_pipeline.py`) reads demo transcripts, extracts structured account memos (JSON), creates the initial Retell Agent Draft Spec (JSON), and saves them to `outputs/accounts/<account_id>/`.
4. **Onboarding Pipeline (v2):** The script reads the onboarding transcripts, extracts new configurations (like exact business hours, routing rules, and emergency definitions), loads the `v1_memo.json`, applies a diff/patch, and generates `v2_memo.json`, `v2_agent_spec.json`, and a `changelog.md`.
5. **Storage:** All artifacts are stored locally in the `outputs/accounts/` directory, serving as our versioned repository.

## 🚀 How to Run Locally

### Prerequisites
- Docker and Docker Compose installed on your machine.

### Step 1: Start n8n
Navigate to the `Clara_Automation` folder and start the customized n8n container:
```bash
cd Clara_Automation
docker-compose up -d --build
```
*(Note: We use a custom Dockerfile to install Python3 into the n8n container so it can run our extraction scripts natively).*

### Step 2: Access n8n and Import Workflow
1. Open your browser and go to `http://localhost:5678`.
2. Skip the onboarding/setup if prompted, or create a local account.
3. Go to **Workflows** -> **Add Workflow** -> **Import from File**.
4. Select `workflows/clara_pipeline.json` from this repository.
5. Save the workflow.

### Step 3: Run the Batch Process
1. Inside the n8n workflow, click the **Execute Workflow** button.
2. The workflow will automatically process all transcripts inside the `transcripts/` folder.

## 📂 How to Plug in Dataset Files

1. Save your raw call transcripts as `.txt` files inside the `transcripts/` directory.
2. **Naming Convention:** 
   - Demo calls must be named: `<account_id>_demo.txt` (e.g., `ben_demo.txt`)
   - Onboarding calls must be named: `<account_id>_onboarding.txt` (e.g., `ben_onboarding.txt`)
3. Rerun the n8n workflow to process the new files.

## 💾 Where Outputs are Stored

All generated JSONs and changelogs are stored in the mapped volume:
`outputs/accounts/<account_id>/`

Inside each account folder, you will find:
- `v1_memo.json` (Demo extraction)
- `v1_agent_spec.json` (Preliminary Agent)
- `v2_memo.json` (Updated with Onboarding data)
- `v2_agent_spec.json` (Production-ready Agent)
- `changelog.md` (Human-readable diff of changes)

## ⚠️ Known Limitations
- **Rule-Based Extraction:** Because we adhered strictly to the "Zero Spend" constraint, the extraction is currently rule-based and expects certain keywords (e.g., "hours are", "emergency", "transfer"). It cannot infer abstract meaning as well as an LLM.
- **Audio Transcription:** Audio files (mp4/m4a) must be pre-transcribed before being placed in the `transcripts/` folder. A local Whisper pipeline was omitted here to avoid massive Docker image sizes and GPU requirements, adhering to a lightweight zero-cost footprint.

## 🌟 What I Would Improve with Production Access

1. **LLM Integration:** I would replace the Python rule-based extraction script with an LLM node in n8n (using OpenAI GPT-4o or Anthropic) using structured JSON output mode to accurately extract complex edge cases, ambiguities, and implicit intents from raw, messy human conversations.
2. **Automated Transcription:** Integrate a webhook to receive audio files directly from Fireflies/Zoom, pass them to an API like Deepgram or AssemblyAI, and automatically feed the transcript into this pipeline.
3. **Database Integration:** Move from local JSON files to a managed database like Supabase (PostgreSQL). We could store `Account` records and versioned configurations, allowing a frontend dashboard to visualize the diffs.
4. **Retell API Integration:** Use n8n's HTTP Request node to automatically push the `v2_agent_spec.json` payload directly to Retell's `POST /create-agent` API endpoint, fully automating the deployment.
5. **Task Tracking:** Add an Asana or Jira node to automatically generate a ticket for the implementation team when a `questions_or_unknowns` array contains missing critical data.