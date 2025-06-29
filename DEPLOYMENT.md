# Deploying to Koyeb

This guide provides step-by-step instructions for deploying the Twitter/X Video Downloader Bot to [Koyeb](https://koyeb.com). The application is already containerized with a `Dockerfile`, which makes the deployment process straightforward.

## Prerequisites

1.  **A GitHub Repository**: You need to have your bot's code pushed to a GitHub repository.
2.  **A Koyeb Account**: Sign up for a free Koyeb account if you don't have one.

## Deployment Steps

### 1. Create a New App on Koyeb

- Log in to your Koyeb account.
- Click the **Create App** button on the dashboard.

### 2. Choose the Deployment Method

- Select **GitHub** as your deployment method.
- If you haven't already, connect your GitHub account to Koyeb and grant it access to the repository containing your bot.
- Choose the correct repository and branch (e.g., `main`).

### 3. Configure the Service

Koyeb will automatically detect the `Dockerfile` in your repository.

- **Service Name**: You can give your service a name, like `telegram-bot`.
- **Docker**: The builder should be set to `Dockerfile`, which is usually detected automatically.
- **Port**: The application listens on port `8000` by default. Koyeb should detect this from the `Dockerfile` (`EXPOSE 8000`). Ensure the port is set to `8000`.
- **Instance Type**: The free `eco` instance type is sufficient to run this bot.

### 4. Set Environment Variables

This is the most critical step. You need to configure the bot's environment variables with your secrets.

- In the "Environment variables" section, click **Add Variable** for each of the following:
  - `BOT_TOKEN`: Your Telegram bot token from BotFather.
  - `RATE_LIMIT_PER_HOUR`: (Optional) Set the number of downloads per hour. Defaults to `5`.
  - `LOG_LEVEL`: (Optional) Set the logging level. Defaults to `INFO`.
  - `WEBHOOK_URL`: **Leave this blank for the initial deployment.** We will set it in the next step.

### 5. Deploy the Application

- Click the **Deploy** button.
- Koyeb will start building your application from the `Dockerfile` and deploy it. You can monitor the progress in the deployment logs.

### 6. Set the Webhook

Once the initial deployment is successful, your application will have a public URL.

1.  **Find Your Public URL**: Go to your service's page on the Koyeb dashboard. The public URL will be displayed (e.g., `https://your-app-name-your-org.koyeb.app`).
2.  **Update the `WEBHOOK_URL`**:
    - Go back to your service's "Settings" tab in Koyeb.
    - Find the `WEBHOOK_URL` environment variable you created earlier.
    - Click to edit it and set its value to your public URL (e.g., `https://your-app-name-your-org.koyeb.app`).
    - **Important**: Make sure there is no trailing slash (`/`).
3.  **Redeploy**: Koyeb will automatically trigger a new deployment with the updated environment variable.

Once the new version is live, the bot will automatically set the webhook and be ready to receive updates from Telegram.

## Verifying the Deployment

- **Check the Logs**: Monitor the runtime logs on Koyeb. You should see a log message confirming the webhook was set, like `INFO: Webhook set to https://your-app-name-your-org.koyeb.app`.
- **Test the Bot**: Send a command like `/start` to your bot in Telegram. It should respond immediately.

That's it! Your Telegram bot is now running on Koyeb.
