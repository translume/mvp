# Run Translume with Docker and OpenAI

## 1. Install and start Docker

Install [Docker Desktop](https://docs.docker.com/get-started/get-docker/) for your laptop and start it. On Linux, Docker Engine with the Compose plugin also works. Docker must be running Linux containers.

Open a terminal and check:

```sh
docker version
docker compose version
```

Both commands must succeed. The application runs on CPU. All learned-model inference, including document understanding, embeddings, evidence judging, and report generation, uses your OpenAI API account.

Leave sufficient RAM and free disk space available to Docker. The initial setup downloads the real scientific reference data and container images. The three DepMap matrices alone total about 4.1 GB; OptimusKG, Reactome, database storage, and images require additional space. These are reference datasets, not locally executed models.

## 2. Extract the project

Extract the supplied ZIP. Open a terminal in the extracted `mvp-main` folder, the folder containing `docker-compose.yml` and this README.

## 3. Create your environment file

On macOS or Linux:

```sh
cp .env.example .env
```

In Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Open `.env` in a text editor. Set the empty `OPENAI_API_KEY=` entry to your actual OpenAI project API key, then save the file. Do not add spaces around `=`. The key must have API billing/quota and access to the configured models.

The included model settings are ready to use:

```dotenv
OPENAI_REASONING_MODEL=gpt-6-astra
OPENAI_DOCUMENT_MODEL=gpt-6-astra
OPENAI_REASONING_EFFORT=xhigh
OPENAI_EMBEDDING_MODEL=text-embedding-3-large
OPENAI_EMBEDDING_DIMENSIONS=1536
OPENAI_REQUEST_TIMEOUT_SECONDS=900
```

The application sends `reasoning.mode=pro` to the Responses API. Keep the defaults for the intended Astra Pro workflow. The API key remains in your local `.env`; it is not copied into the Docker images.

## 4. Build and start the application

From the project folder, run:

```sh
docker compose up --build -d
```

The first startup builds the CPU images, starts the databases, downloads the required MedeaDB and OptimusKG datasets, validates those files, and creates the database schema and search indexes. It then starts the document, evidence, API, UI, and report services. Existing complete data is reused on subsequent starts.

The build and initial downloads can take considerable time. To see progress from another terminal in the same folder:

```sh
docker compose logs --tail=100 -f data-init
```

Press Ctrl+C to stop following the log. This leaves the containers running.

Check startup status:

```sh
docker compose ps -a
```

`data-init` should show `Exited (0)`. The application services should become healthy. Startup deliberately fails if the real datasets, required services, or OpenAI model access are unavailable.

If startup stops, inspect the failing service before retrying:

```sh
docker compose logs --tail=200 data-init translume-api tooluniverse-service medea-service
```

For an OpenAI authentication, permission, or quota error, correct the key or account access and rerun `docker compose up --build -d`. For a data download error, restore access to the reported Hugging Face or Harvard Dataverse URL and rerun the same command. A failed download is never replaced with sample data. For a container killed because of insufficient memory, increase Docker's memory allocation and restart it.

## 5. Generate your report

Open [http://localhost:7860](http://localhost:7860) in your browser.

1. Upload your actual oncology report PDF under **Oncology report PDF** (maximum 100 MB and 500 pages).
2. Choose the matching **Report type**.
3. Enter the report's actual **Diagnosis**.
4. Click **Generate report and pathway analysis** once.
5. Leave the page open while the application processes the report, retrieves evidence, and completes the remote OpenAI stages. Long reasoning and research runs can take substantial time.
6. Review the **Pathway analysis**, **Clinical review**, **Technical audit**, and **Raw packet** tabs. The workflow retains human validation; model-generated hypotheses require review.

To follow processing:

```sh
docker compose logs --tail=100 -f translume-api docling-service medea-service precision-oncology-pipeline dynamic-pathway-analyzer
```

## 6. Save the results

In **Pathway analysis**, click **Download Pathway Analysis PDF**, then download the generated file. It contains the pathway analysis, research memo, and tumor-board causal summary.

In **Technical audit**, click **Fetch technical packet export** to download the persisted packet JSON, including provenance and review information. The **Clinical review** tab retains the reviewer decision controls.

The full downstream files are also written to `data/artifacts` in the extracted project folder, grouped by session and run. Uploaded reports, review records, search indexes, scientific datasets, and API audit journals persist in Docker volumes.

## 7. Run the real end-to-end verification when required

This optional command makes additional billable OpenAI calls and processes a real report through the same services.

Create `data/input` inside the project folder and place your actual readable PDF there with the filename `report.pdf`. In `.env`, set `TRANSLUME_E2E_REPORT_TYPE` to the matching report type and fill `TRANSLUME_E2E_DIAGNOSIS` with the actual diagnosis.

Run:

```sh
docker compose --profile verification run --rm verify
```

The command checks service health, actual Astra Pro structured output, actual OpenAI embeddings, report processing, remote-call provenance, database/search persistence, a `needs_review` validation round trip, and the three downstream report artifacts. Success is a JSON result with `"status": "ok"` and a zero exit code. A failed check exits nonzero; inspect the reported error and service logs. No demonstration report or fabricated result is supplied.

## 8. Stop and restart

Stop the application while retaining data:

```sh
docker compose down
```

Start it again from the same project folder:

```sh
docker compose up --build -d
```

Keep the extracted project folder and its `data/artifacts` directory. Do not add `--volumes` or `-v` to the stop command unless you intend to delete the stored databases and reference data.
