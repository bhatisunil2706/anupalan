---
title: Security training
section: People and training
order: 20
summary: Built-in and company courses, required training by department, due dates for new joiners, certificates, team progress and imports.
routes: /training, /training/*
---

Security and privacy awareness training is required by almost every framework (HR-03). The platform runs the whole programme: courses, who must take what, reminders, certificates and the report your auditor asks for.

## The four tabs

| Tab | Who sees it | What it's for |
| --- | --- | --- |
| My learning | Everyone | Your assigned courses, due dates and certificates; optional courses |
| Team progress | Admins and auditors | Who has completed what, by department and person; exports and imports |
| Courses and assignments | Admins | Choose which courses are required and for whom; create company courses |
| Phishing simulations | Admins | See [Phishing simulations](/docs/phishing-simulations) |

## Built-in courses

| Course | Category | Minutes |
| --- | --- | ---: |
| Security essentials | Foundations | 12 |
| Spotting phishing and social engineering (with practice exercises) | Foundations | 10 |
| Passwords, MFA and keeping your accounts safe | Foundations | 8 |
| UPI, KYC and 'digital arrest' scams (with practice exercises) | Foundations | 10 |
| Spotting and reporting security incidents | Foundations | 7 |
| Using AI tools safely at work | Foundations | 8 |
| Working securely from home and on the move | Foundations | 7 |
| India's DPDP Act for everyone at work | Privacy | 15 |
| Classifying and sharing data safely | Privacy | 8 |
| Secure development for engineers | Role-based | 15 |
| Payment fraud and business email compromise (with practice exercises) | Role-based: finance and procurement | 10 |
| Handling personal data in customer support | Role-based: support and operations | 10 |

Each course has a short lesson and a five-question quiz with a pass mark (usually 80%). Answers are shuffled, the correct answers stay on the server, and after submitting you see an explanation for each question. Some courses have **practice exercises**: realistic messages to judge as phishing or legitimate, which don't count towards the score.

## Who must take what

In **Courses and assignments**, each course is either **optional** or **required**. For a required course you set:

- **who**: everyone, or only certain departments from the HR roster;
- **days to complete** (default 30);
- **renew every** (default 12 months).

Security essentials, the phishing course and DPDP basics are required for everyone by default. If your roster has Engineering, Finance or Support departments, the matching role-based courses are required for them automatically.

### Due dates

- **New joiners** get the full number of days from their **joining date**.
- **Existing staff** get the full number of days from the date the course became required.
- Someone who **clicks a phishing simulation** can be enrolled in the phishing course with 14 days to complete it, even if they passed it before.

Completions expire after the renewal period, and the person is asked to take the course again.

## Certificates

Passing a course produces a certificate with the person's name, course, score, completion date, valid-until date and a certificate ID. Open it from the course or the course card, then **Print or save as PDF**.

## Team progress

- **Everyone fully trained**: the percentage of all staff, including people in the HR roster who don't have an account yet. Auditors expect every employee to be trained.
- **People with an account fully trained**.
- **In the HR roster without an account**, with **Invite them** to email everyone missing an invitation.
- Completion **by department**, with overdue counts. Click a department to filter.
- A table of every person and their status for each required course: Completed, To do, Overdue, Renewal due or Not passed.

**Export CSV** gives the auditor-ready report: name, email, department, course, status, due date, last completion and score.

## Importing from another learning platform

If people completed training elsewhere, **Import from another LMS** accepts a CSV with columns `email`, `course` (the course name or ID) and `completed_at`, plus `score` if you have it. Imported completions count like any other.

## Company courses

**Create a course** to teach your own policies, tools or client requirements. Add a title and summary, write the content (paste from Google Docs or Word, or import a document), optionally link a video (https), and build a quiz: questions with 2 to 6 options and an explanation. Save as a draft, then **Publish** and assign it like any other course.

## Reminders and the HR-03 check

Each person with overdue or expired required training receives a weekly reminder. Every day the platform checks whether at least 90% of staff are fully trained, and records the result as an automated check on **HR-03**, so the control's health reflects reality.
