# OPELSS

# Remote repo: https://github.com/Mbuyelomuremela-lab/opelss_temp.git

OPELSS is a modular enterprise Flask application for the OAU-PID e-Lab Support System.

## Features

- Role-based access control for Admin, HQ Trainee, and Lab Trainee
- Geolocation-protected lab trainee login
- Attendance clock-in/out with audit tracking and PDF export
- Asset, visitor, enquiry, programme, and announcement management
- Excel exports using OpenPyXL
- Report generation for attendance, assets, visitors, programmes, labs, and provinces
- Responsive Bootstrap 5 UI
- Production deployment support via Vercel

## Setup

1. Copy `.env.example` to `.env` and set `DATABASE_URL` and `SECRET_KEY`
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. For a new, empty local database only, initialize the schema:
   ```bash
   flask db upgrade
   ```
   Do not run these commands against the existing production database. Vercel
   startup skips table creation, data seeding, and schema changes.
4. Run the app locally:
   ```bash
   python run.py
   ```

## Deploy to Vercel

- Import the new GitHub repository as a Vercel project. Vercel detects the Flask
  app exported as `app` from `wsgi.py`.
- Set `DATABASE_URL` to the existing Azure PostgreSQL connection string and
  `SECRET_KEY` to a strong, private random value in the Vercel project's
  Production environment. Do not commit either value. Preview deployments also
  require variables; do not point previews at production unless you intend
  preview users to read and change production data.
- Redeploy after setting the variables. The app will require both variables on
  Vercel and will connect to the existing database without creating tables,
  seeding rows, or running migrations.
- Python 3.12 is selected by `.python-version`.
- Set the Vercel Function region close to the Azure PostgreSQL server. Azure
  firewall rules must also allow Vercel egress; Vercel's outbound IPs are not
  fixed by default, so IP-restricted database access may require Vercel Static
  IPs or an alternative network configuration.
- Announcement poster uploads use `/tmp` on Vercel and are temporary. Uploaded
  files can disappear between function invocations; use persistent object
  storage if poster persistence is required.

## Notes

- Lab Trainee login requires browser geolocation access
- Admin can create users and manage labs, provinces, and announcements
- Public landing page includes an announcements carousel and enquiry tracking form
