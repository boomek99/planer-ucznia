# Planer ucznia — Librus API

GitHub Pages hosts the static frontend. The Librus feature needs a separate Python API so passwords do not end up in the public source code or Supabase database.

## Deploy the API on Render

1. Sign in to Render and connect the GitHub account that owns this repository.
2. Choose **New → Blueprint**, select `boomek99/planer-ucznia`, and let Render read `render.yaml`.
3. Select the free web-service plan. Enter these environment values when prompted:
   - `SUPABASE_URL`: the project's URL
   - `SUPABASE_PUBLISHABLE_KEY`: the project's public publishable key (`sb_publishable_...`)
4. Wait until the deployment is successful. Open `/health` on the service URL and check that it returns `ok: true` and `librus_configured: true`.
5. Copy the service's HTTPS URL. Replace `UZUPELNIJ_ADRESEM_API` in `index.html` with that URL and commit the change. Do not add a trailing slash.

The API checks each user's Supabase access token, limits repeated attempts, configures browser CORS for this GitHub Pages origin, and never stores Librus passwords or schedule data. The password is sent over HTTPS to this API for one request, so students should use it only if they trust the person or organization operating the Render service.

## Librus limitations

The supplied `librus-apix` client is an unofficial scraper that uses a Librus login and password; Librus OAuth is not implemented or claimed here. Students must enter their Librus credentials again for each fetch. The API returns schedule events to the signed-in student but does not yet sync them to Google Calendar.

Render's free web services can spin down after 15 minutes of inactivity and may take time to wake. Render documents free instances as suitable for hobby projects and previews, not production use. Do not use this setup for a school-wide production service without reviewing the hosting, privacy, security, and Librus terms first.
