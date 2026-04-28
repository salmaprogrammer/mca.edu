# MCA Academy System

A comprehensive student management system for MCA Academy built with Streamlit and Google Sheets integration.

## Features

- **Role-based Access Control**
  - Admin Dashboard: System management and reporting
  - Teacher Dashboard: Attendance tracking, grade management, WhatsApp notifications
  - Assistant Dashboard: Student registration
  - Parent/Student Portal: Progress tracking and attendance history

- **Real-time Data Management**
  - Google Sheets integration for data storage
  - Automatic sheet initialization with proper headers
  - Live attendance and grade tracking

- **Student Management**
  - Register new students with course assignments
  - Track payment status and course rounds
  - Monitor remaining sessions per round

- **Communication**
  - WhatsApp integration for parent notifications
  - Automated attendance and grade reports

## Installation

### Local Development

1. Clone the repository:
```bash
git clone https://github.com/yourusername/mca-academy-system.git
cd mca-academy-system
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Set up Google Sheets credentials:
   - Create a Google Cloud service account
   - Download the JSON credentials file
   - Save it as `mca.json` in the project directory (never commit this file!)

5. Run the app:
```bash
streamlit run app.py
```

The app will be available at `http://localhost:8501`

### Streamlit Cloud Deployment

1. Push your code to GitHub
2. Go to [Streamlit Cloud](https://share.streamlit.io)
3. Sign in with your GitHub account
4. Click "New app" and select your repository
5. Set the main file path to `app.py`
6. Add your Google Sheets credentials as a secret:
   - Go to App settings → Secrets
   - Paste your credentials JSON in TOML format

## Configuration

### Spreadsheet Setup

The app expects a Google Sheet with the following structure:

**Students Sheet:**
- Name
- Phone
- Parent_Phone
- Round
- Sessions
- Teacher
- Payment_Status
- Date_Registered

**Attendance Sheet:**
- Student_Name
- Date
- Status (حاضر/غائب)
- Grade
- Homework

### Credentials

Ensure your Google Sheets credentials are properly configured in Streamlit secrets or `mca.json`

## Usage

### Login Credentials (Development)
- **Admin:** username: `admin` | password: `mca2026`
- **Teacher:** username: `teacher` | password: `mca_teacher`
- **Assistant:** username: `assistant` | password: `mca_asst`
- **Parent/Student:** Phone number as both username and password

## Project Structure

```
mca-academy-system/
├── app.py                 # Main Streamlit application
├── mca.json              # Google Sheets credentials (not committed)
├── requirements.txt      # Python dependencies
├── .streamlit/
│   ├── config.toml      # Streamlit configuration
│   └── secrets.toml     # Secrets (not committed)
└── README.md            # This file
```

## Technologies Used

- **Streamlit**: Web app framework
- **Google Sheets API**: Data storage and management
- **gspread**: Google Sheets Python client
- **pandas**: Data processing
- **oauth2client**: Google authentication

## Security Notes

- ⚠️ Never commit `mca.json` or `.streamlit/secrets.toml`
- Use `.gitignore` to exclude sensitive files
- On Streamlit Cloud, use Secrets management feature
- Change default credentials before production use

## Support

For issues or questions, please open an issue on GitHub.

## License

This project is licensed under the MIT License.
