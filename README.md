# Clara AI – Automated Onboarding & Agent Configuration Pipeline

An end-to-end automation system that converts raw call transcripts into structured operational rules and production-ready AI voice agent configurations. Built for the Clara AI Technical Associate assignment.

## 🏗 Architecture & Data Flow

This pipeline uses **n8n** (self-hosted via Docker) as the workflow orchestrator and **Google Gemini Flash** (free tier) for intelligent transcript extraction. The system processes demo and onboarding call recordings/transcripts to generate versioned Retell Agent configurations.

```
┌─────────────────────────────────────────────────────────────────────┐
│                      n8n Workflow (20+ Nodes)                       │
│                                                                     │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────────┐     │
│  │ Trigger   │──▶│ List &   │──▶│ Route    │──▶│ Gemini Flash │     │
│  │ (Manual/  │   │ Parse    │   │ Demo vs  │   │ Extraction   │     │
│  │  Webhook) │   │ Files    │   │ Onboard  │   │ (Python)     │     │
│  └──────────┘   └──────────┘   └──────────┘   └──────┬───────┘     │
│                                                       │             │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────▼───────┐     │
│  │ Save     │◀──│ Google   │◀──│ Check    │◀──│ Generate     │     │
│  │ Summary  │   │ Calendar │   │ Appoint- │   │ Agent Spec   │     │
│  │ Report   │   │ Event    │   │ ments    │   │ (v1/v2)      │     │
│  └──────────┘   └──────────┘   └──────────┘   └──────────────┘     │
└─────────────────────────────────────────────────────────────────────┘
```

### Pipeline A: Demo → v1 Agent
1. **Ingest** demo transcript
2. **Extract** structured account memo using Gemini Flash
3. **Generate** v1 Retell Agent Draft Spec
4. **Store** artifacts to `outputs/accounts/<account_id>/`

### Pipeline B: Onboarding → v2 Agent
1. **Load** existing v1 memo
2. **Extract** onboarding updates using Gemini Flash
3. **Merge** updates → v2 memo (with diff/patch)
4. **Regenerate** v2 agent spec
5. **Generate** changelog
6. **Optionally** create Google Calendar event for scheduled appointments
7. **Optionally** push to Retell AI

## 🚀 Quick Start

### Prerequisites
- Docker & Docker Compose
- A free Google Gemini API key ([get one here](https://aistudio.google.com/app/apikey))

### Step 1: Configure API Keys
```bash
cd Clara_Automation
cp .env.example .env
# Edit .env and add your GEMINI_API_KEY
nano .env
```

### Step 2: Start n8n
```bash
docker-compose up -d --build
```
*(First build installs Python3 + Gemini SDK into the n8n container.)*

### Step 3: Import & Run the Workflow
1. Open `http://localhost:5678` in your browser
2. Create a local account (or skip onboarding)
3. Go to **Workflows** → **Add Workflow** → **Import from File**
4. Select `workflows/clara_pipeline.json`
5. Save the workflow
6. Click **Execute Workflow** ▶️

### Step 4: Google Calendar Setup (Optional)
1. In n8n, go to **Settings** → **Credentials** → **Add Credential**
2. Select **Google Calendar OAuth2 API**
3. Follow the OAuth flow to connect your Google account
4. Update the Calendar nodes in the workflow with your credential

### Alternative: Run Batch Script Directly
```bash
# Local (requires Python 3.8+ and pip install google-generativeai requests)
export GEMINI_API_KEY=your_key_here
bash scripts/run_batch.sh transcripts outputs/accounts

# Inside Docker
docker exec -it clara_automation-n8n-1 bash /data/scripts/run_batch.sh /data/transcripts /data/outputs/accounts
```

## 📂 How to Plug in Dataset Files

1. Save transcript `.txt` files in the `transcripts/` directory
2. **Naming Convention:**
   - Demo: `<account_id>_demo.txt` (e.g., `ben_demo.txt`)
   - Onboarding: `<account_id>_onboarding.txt` (e.g., `ben_onboarding.txt`)
3. Run the n8n workflow or batch script to process

## 💾 Output Structure

```
outputs/accounts/<account_id>/
├── v1_memo.json          # Demo extraction (account memo)
├── v1_agent_spec.json    # Preliminary Retell Agent
├── v2_memo.json          # Updated with onboarding data
├── v2_agent_spec.json    # Production-ready Agent
├── changelog.md          # Human-readable v1 → v2 diff
└── retell_metadata.json  # (Optional) Retell deployment info
```

### Account Memo Fields
| Field | Description |
|-------|-------------|
| `account_id` | Unique account identifier |
| `company_name` | Business name |
| `business_hours` | Days, times, timezone |
| `office_address` | Physical address |
| `services_supported` | List of services offered |
| `emergency_definition` | What triggers an emergency |
| `emergency_routing_rules` | Who to call, fallback logic |
| `non_emergency_routing_rules` | After-hours non-emergency handling |
| `call_transfer_rules` | Timeouts, retries, fallback |
| `integration_constraints` | CRM/system rules |
| `after_hours_flow_summary` | After-hours call flow |
| `office_hours_flow_summary` | Business hours call flow |
| `questions_or_unknowns` | Missing data flagged for review |

## 🔧 n8n Workflow Nodes

The workflow contains **20+ nodes** organized in this flow:

| # | Node | Purpose |
|---|------|---------|
| 1 | 🔧 Manual Trigger | Start batch processing |
| 2 | 🌐 Webhook Trigger | Alternative HTTP trigger (disabled by default) |
| 3 | ⚙️ Set Config | Load API keys and paths |
| 4 | 📁 List Transcript Files | Scan `/data/transcripts/*.txt` |
| 5 | 🔀 Parse & Sort Files | Extract account_id and type, sort demos first |
| 6 | 📦 Process One-by-One | Batch processor (one file at a time) |
| 7 | 📋 Demo or Onboarding? | Route by file type |
| 8 | 🧠 Run Demo Pipeline | Execute Python pipeline (demo → v1) |
| 9 | 🧠 Run Onboarding Pipeline | Execute Python pipeline (onboarding → v2) |
| 10-11 | 📊 Parse Results | Parse JSON output from pipeline |
| 12-13 | 📅 Check for Appointments | Read memo for appointment data |
| 14-15 | 📅 Has Appointment? | Route to calendar or skip |
| 16-17 | 📆 Create Calendar Event | Create Google Calendar event |
| 18-19 | ⏭️ No Appointment | Pass-through for files without appointments |
| 20 | 📋 Log Result | Aggregate processing results |
| 21 | 📊 Batch Summary Report | Generate final summary |
| 22 | 💾 Save Summary | Write summary to `outputs/last_run_summary.json` |

## ⚠️ Known Limitations

- **Gemini Rate Limits**: Free tier allows 15 RPM. Batch processing of 10+ files may need brief pauses.
- **Audio Transcription**: Audio files (mp4/m4a) must be pre-transcribed. Use AssemblyAI (free tier) or local Whisper.
- **Google Calendar**: Requires OAuth2 setup in n8n. Without it, appointment detection still works but calendar events aren't created.
- **Retell Free Tier**: If programmatic agent creation isn't available, the pipeline outputs the Agent Draft Spec JSON for manual import into the Retell UI.

## 🌟 What I Would Improve with Production Access

1. **Real-time Voice Integration**: Connect Twilio webhooks → n8n → Gemini for live call handling with STT/TTS
2. **Database Backend**: Replace JSON files with Supabase (PostgreSQL) for versioned account configs
3. **Automated Transcription**: Webhook from Fireflies/Zoom → Deepgram/AssemblyAI → auto-feed pipeline
4. **Retell API Direct Push**: Auto-deploy v2 agent specs to Retell's API
5. **Task Tracking**: Asana/Jira node for auto-generating tickets when `questions_or_unknowns` has items
6. **Dashboard**: Web UI for viewing account status, diffs, and agent deployment history
7. **Diff Viewer**: Side-by-side visual comparison of v1 vs v2 agent prompts

## 💰 Cost Breakdown

| Service | Tier | Cost |
|---------|------|------|
| n8n (self-hosted Docker) | Free | $0 |
| Google Gemini Flash | Free (15 RPM) | $0 |
| Google Calendar API | Free | $0 |
| AssemblyAI (transcription) | Free tier | $0 |
| Retell AI | Free tier | $0 |
| **Total** | | **$0** |