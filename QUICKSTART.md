# Docker quick start

Follow [README.md](README.md) for the complete laptop instructions.

1. Install and start Docker with Compose.
2. Extract the project and open a terminal in `mvp-main`.
3. Copy `.env.example` to `.env` and set your actual `OPENAI_API_KEY`.
4. Run `docker compose up --build -d`.
5. Wait for `data-init` to exit successfully and the application services to become healthy.
6. Open http://localhost:7860, upload your actual PDF, choose its report type, enter the diagnosis, and click **Generate report and pathway analysis**.
7. Download the PDF and technical packet; downstream files also persist under `data/artifacts`.

The default deployment runs all learned inference on OpenAI using Astra Pro and `text-embedding-3-large`. The laptop runs the application, databases, source-data lookups, and PDF rendering on CPU. No host Python, Git, model server, or GPU installation is needed.

For a real automated verification with your own PDF and diagnosis, follow step 7 of the README. This performs paid API calls and exits nonzero on a failed check.
