🔧 Google Docs Sync Integration
Purpose: To synchronize Google Docs from a specific folder in Google Drive into your local application, converting them into Markdown files for further processing.
Key Components:
Environment Variables:
GOOGLE\_CREDS\_JSON: Base64-encoded Google OAuth 2.0 credentials JSON.
GOOGLE\_TOKEN\_JSON: Base64-encoded token JSON obtained after user authorization.
File Paths:
CREDENTIALS\_PATH: Path to store decoded credentials (/tmp/credentials.json).
TOKEN\_PATH: Path to store decoded token (frontend/sync/token.json).
IMPORT\_PATH: Directory to store imported Markdown files (docs/imported).
Folder Configuration:
COMMAND\_CENTER\_FOLDER\_NAME: Name of the folder in Google Drive to sync (COMMAND\_CENTER).
Workflow:
Credential Handling:
Check if CREDENTIALS\_PATH exists. If not, decode GOOGLE\_CREDS\_JSON and write to this path.
Check if TOKEN\_PATH exists. If not, decode GOOGLE\_TOKEN\_JSON (if available) and write to this path.
Authentication:
If TOKEN\_PATH exists, load credentials from it.
If credentials are invalid or don't exist:
Initiate OAuth flow using InstalledAppFlow.from\_client\_secrets\_file.
Run local server to obtain user authorization and generate new token.
Save new token to TOKEN\_PATH.
Google Drive Interaction:
Build drive\_service and docs\_service using authenticated credentials.
Locate the folder ID for COMMAND\_CENTER\_FOLDER\_NAME.
Retrieve all Google Docs within this folder.
For each document:
Fetch content using docs\_service.
Convert content to Markdown using markdownify.
Save the Markdown file to IMPORT\_PATH.
🛠️ Error Handling and Debugging
Common Issues Encountered:
Missing Environment Variables:
Error: ❌ Missing GOOGLE\_CREDS\_JSON in environment variables
Solution: Ensure that GOOGLE\_CREDS\_JSON is correctly set in your environment.
Syntax Errors:
Error: SyntaxError: 'return' outside function
Cause: Incorrect indentation or misplaced return statement.
Solution: Ensure that all code blocks are properly indented and that return statements are within function scopes.
Attribute Errors:
Error: AttributeError: 'InstalledAppFlow' object has no attribute 'run\_console'
Cause: Incorrect method used for initiating OAuth flow.
Solution: Use run\_local\_server(port=0) instead of run\_console() for local development.
OAuth Redirect URI Mismatch:
Error: Error 400: redirect\_uri\_mismatch
Cause: The redirect URI used in the application doesn't match any of the authorized redirect URIs in the Google Cloud Console.
Solution:
Navigate to Google Cloud Console Credentials page.
Select your OAuth 2.0 Client ID.
In the "Authorized redirect URIs" section, add the exact redirect URI used by your application (e.g., http://localhost:8080/).
Save the changes.
🔄 Full Sync Process
Endpoint: POST /docs/full\_sync
Functionality:
Initiates the Google Docs synchronization process.
Embeds the synchronized Markdown documents into the knowledge base.
Logs the synchronization activity for auditing and tracking purposes.serverfault.com