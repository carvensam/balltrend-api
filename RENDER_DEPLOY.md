# BallTrend API — Render Deployment

## Render Blueprint (render.yaml)

This repository is ready for deployment on [Render](https://render.com) using Docker.

### Manual Deployment Steps

1. **Push this code to GitHub**
   ```bash
   # If you haven't already created a GitHub repo:
   # Go to https://github.com/new and create a public repo named "balltrend-api"
   
   git remote add origin https://github.com/YOUR_GITHUB_USERNAME/balltrend-api.git
   git branch -M main
   git push -u origin main
   ```

2. **Create Web Service on Render**
   - Go to [https://dashboard.render.com](https://dashboard.render.com)
   - Click **New +** → **Web Service**
   - Connect your GitHub repo `balltrend-api`
   - Render will auto-detect the `Dockerfile`
   - Select **Free** plan
   - Click **Create Web Service**

3. **Get your service URL**
   - After deployment, Render will give you a URL like:
     `https://balltrend-api.onrender.com`
   - Note this URL — you'll need it for the Android app

4. **Health check**
   - Visit `https://YOUR_URL/api/v1/health` in browser
   - Should return: `{"status":"ok","version":"v1"}`

### Render Blueprint (Alternative)

If you prefer using a Blueprint, copy `render.yaml` to your repo root and click **New +** → **Blueprint** in the Render dashboard.

---

### ⚠️ Important Notes

- **Free tier limitation**: The service sleeps after 15 minutes of inactivity. First request after sleep may take 30-60 seconds to wake up.
- **SQLite data**: The database (`data/soccer_patterns.db`) is baked into the Docker image. It will persist across requests but will reset if you redeploy. To update data, modify the DB locally, commit, and redeploy.
- **No persistent disk on Free tier**: Any runtime changes to the database will be lost on sleep/restart.

---

### Android App Configuration

Once you have the Render URL, update `RetrofitClient.kt` in your Android project:

```kotlin
// Before (local development)
// private const val DEFAULT_URL = "http://192.168.x.x:5000/"

// After (Render deployment)
private const val DEFAULT_URL = "https://balltrend-api.onrender.com/"
```

Then rebuild the APK.
