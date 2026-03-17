# 🚀 GitHub Webhook Setup Guide

To enable automatic code analysis whenever a new Pull Request is opened or updated, follow these steps.

## 1. Expose your Local Server
Since GitHub needs to send a request to your local machine, you must expose your port `8000`. We recommend **ngrok**.

1.  **Install ngrok**: [Download here](https://ngrok.com/download)
2.  **Run ngrok**:
    ```powershell
    ngrok http 8000
    ```
3.  **Copy the Forwarding URL**: It will look like `https://a1b2-c3d4.ngrok.io`.

## 2. Configure GitHub Webhook
1.  Go to your GitHub Repository → **Settings** → **Webhooks** → **Add webhook**.
2.  **Payload URL**: `<your-ngrok-url>/github-webhook`
3.  **Content type**: `application/json`
4.  **Secret**: Enter your `GITHUB_WEBHOOK_SECRET` (found in your `.env` file). Default is `code_analyzer_secret`.
5.  **Which events?**: Select **"Let me select individual events"** → Check **"Pull requests"**.
6.  **Active**: Ensure this is checked.
7.  Click **Add webhook**.

## 3. Verify System Connectivity
You can test if your backend is ready to receive requests BEFORE setting up ngrok by using the provided test script:

```powershell
# Ensure your FastAPI server is running in another terminal
.\venv\Scripts\python scripts/test_webhook.py
```

If successful, you will see `Status: 202` and `Analysis started`.

## 4. Triggering Analysis
Now, whenever someone:
*   Opens a new PR
*   Pushes new code to an existing PR
*   Reopens a closed PR

The **Code AI Analyzer** will automatically start the review and post its findings back to the PR!
