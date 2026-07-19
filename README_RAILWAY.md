# Ekhishini Lamajita — Railway deployment

This version deploys through a Dockerfile using Python 3.11.

## Files that must be in the GitHub repository root

- Dockerfile
- railway.json
- DASH.py
- data_service.py
- requirements.txt
- Stokvel_20260719.xlsx
- assets/dashboard.css
- assets/logoekhishishini.jpeg

## Railway variables

Add these variables in Railway under the service's Variables tab:

- DATA_URL=https://raw.githubusercontent.com/leko94/ARISE_DASH_DASHBOARD/main/Stokvel_20260719.xlsx
- EXCEL_FILE=Stokvel_20260719.xlsx
- SHEET_NAME=Sheet1
- REFRESH_SECONDS=60

Optional password protection:

- DASHBOARD_USERNAME=your_username
- DASHBOARD_PASSWORD=your_password

Do not add a PORT variable. Railway supplies PORT automatically.

## Deployment steps

1. Upload the extracted files to the root of the GitHub repository and commit to main.
2. In Railway, choose New Project, then Deploy from GitHub repo.
3. Select ARISE_DASH_DASHBOARD.
4. Add the variables above and deploy.
5. Open the service, choose Settings, then Networking, and select Generate Domain.
6. Test the generated domain and the /health endpoint.
