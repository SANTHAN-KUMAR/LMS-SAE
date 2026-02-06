# AWS Deployment Guide

This guide explains how to deploy the **Examination Middleware** to AWS while connecting to your remote **Neon PostgreSQL** database.

We recommend **AWS App Runner** for the easiest, most modern deployment (serverless container). Alternatively, you can use **AWS EC2** for a standard virtual machine approach.

---

## Prerequisites

1.  **AWS Account**: You need an active AWS account.
2.  **Neon Database Connection**: Have your `DATABASE_URL` ready (`postgresql+asyncpg://...`).
3.  **Code Repository**: Push your code to GitHub (recommended for App Runner).

---

## Option 1: AWS App Runner (Recommended)

App Runner is a fully managed service that makes it easy for developers to deploy containerized web applications and APIs, at scale and with no prior infrastructure experience. It handles load balancing and HTTPS automatically.

### Steps:

1.  **Push Code to GitHub**:
    Ensure your latest code (including `Dockerfile` and `requirements.txt`) is in a GitHub repository.

2.  **Create App Runner Service**:
    - Go to the [AWS App Runner Console](https://console.aws.amazon.com/apprunner).
    - Click **Create service**.
    - **Source**: Select **Source code repository**.
    - **Connect**: Connect your GitHub account and select your repository & branch.
    - **Deployment settings**: Choose **Automatic** (deploys on every push).

3.  **Configure Build**:
    - **Configuration file**: Select **Configure all settings here**.
    - **Runtime**: Select **Python 3**.
    - **Build command**: `pip install -r requirements.txt`
    - **Start command**: `uvicorn app.main:app --host 0.0.0.0 --port 8000`
    - *Alternatively, you can choose "Docker" and point to your Dockerfile, but the Python runtime is often faster/simpler.*

4.  **Configure Service**:
    - **Service name**: `exam-middleware`
    - **Port**: `8000`
    - **Environment variables**: Add the following (copy values from your local `.env`):
        - `DATABASE_URL`: **Important!** Paste your Neon Connection string here.
        - `SECRET_KEY`: Generate a strong random string.
        - `MOODLE_BASE_URL`: URL of your LMS (if available).
        - `MOODLE_ADMIN_TOKEN`: Your Moodle token.
        - `APP_ENV`: `production`

5.  **Deploy**:
    - Click **Create & deploy**.
    - Wait a few minutes. You will get a default domain (e.g., `https://xyz.awsapprunner.com`).

---

## Option 2: AWS EC2 (Docker Compose)

Use this option if you want full control over the server or are using the AWS Free Tier.

### Steps:

1.  **Launch EC2 Instance**:
    - Go to EC2 Console > **Launch Instances**.
    - **OS**: Ubuntu Server 22.04 LTS.
    - **Instance Type**: `t2.micro` or `t3.micro`.
    - **Key Pair**: Create/Select one to SSH into the server.
    - **Security Group**: Allow **SSH (22)**, **HTTP (80)**, and **HTTPS (443)**.

2.  **Connect to Instance**:
    ```bash
    ssh -i your-key.pem ubuntu@your-ec2-ip
    ```

3.  **Install Docker & Git**:
    ```bash
    sudo apt update
    sudo apt install -y docker.io docker-compose git
    sudo usermod -aG docker $USER
    # Log out and log back in for group changes to take effect
    exit
    ssh -i your-key.pem ubuntu@your-ec2-ip
    ```

4.  **Clone & Configure**:
    ```bash
    git clone https://github.com/your-username/exam-middleware.git
    cd exam-middleware
    
    # Create production env file
    cp .env.example .env
    nano .env
    ```
    *Paste your Neon `DATABASE_URL` and other secrets here.*

5.  **Run with Docker Compose**:
    Since we are using an external DB (Neon), we only need the app (and maybe redis/nginx), not the local postgres container.
    
    You can run using the production profile:
    ```bash
    # This command starts app and nginx (if configured), but NOT the local db
    docker-compose --profile production up -d
    ```
    
    *Note: You may need to tweak `docker-compose.yml` to remove the `depends_on: db` if strict dependencies prevent startup. Alternatively, just run the app container standalone:*
    
    ```bash
    docker build -t exam-middleware .
    docker run -d -p 80:8000 --env-file .env --name app exam-middleware
    ```

6.  **Verify**:
    Visit `http://your-ec2-ip` in your browser.

---

## Important Note on "LMS Part"

Since you mentioned the LMS part is hosted elsewhere:
1.  **Do not deploy Moodle**: Our scripts generally assume Moodle is external. You verify this by setting `MOODLE_BASE_URL` in your `.env` to point to the actual external LMS URL.
2.  **Networking**: Ensure your AWS deployment can reach the LMS URL.
