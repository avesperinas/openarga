from __future__ import annotations

from starlette.requests import Request

from gateway import words

ENGLISH = """<h1>arga privacy policy</h1>
<p>Last updated: October 9, 2026.</p>

<p>arga is a private, non-commercial personal system that brings together the data of each person
who uses it: health, finances, notes, calendar and more. Only people invited by its administrator
can use it; it is not open to the public, shows no ads and sells nothing.</p>

<h2>Data processed</h2>
<ul>
<li><strong>Account:</strong> the name and email of the Google account used to sign in.</li>
<li><strong>Data the person enters</strong> in arga's apps.</li>
<li><strong>Data from external sources the person connects</strong> themselves, only while the
connection exists.</li>
</ul>

<h2>Google Health data</h2>
<p>When a person connects Google Health, arga requests <strong>read-only</strong> access to:
activity and fitness (steps, distance, calories, active minutes, floors, VO₂ max, workouts),
health metrics (heart rate, resting heart rate, heart rate variability, oxygen saturation,
respiratory rate, temperature, weight), sleep (duration and stages), profile (age, sex, height) and
location recorded during a workout, to draw its route. arga never writes, changes or deletes
anything in the person's Google Health account.</p>

<h2>How it is used</h2>
<p>Only to show the person their own data: charts, trends, summaries and goals inside arga. If the
person connects an AI assistant to arga themselves, that assistant can read their data when they
ask it to, to answer them. Nothing else.</p>

<h2>What is never done</h2>
<ul>
<li>Data is never sold or transferred to third parties.</li>
<li>It is never used for advertising, commercial profiling, or credit or insurance decisions.</li>
<li>It is never used to train artificial intelligence models.</li>
<li>No user of arga can see another user's data; isolation is enforced by the database.</li>
<li>No human reads it, except at the person's request to fix a problem, for security, or to comply
with the law.</li>
</ul>
<p>arga's use and transfer of information received from Google APIs adheres to the
<a href="https://developers.google.com/terms/api-services-user-data-policy">Google API Services User
Data Policy</a>, including the Limited Use requirements, and to the
<a href="https://developers.google.com/health/policies/health-api-developer-user-data-policy">Google
Health API Developer and User Data Policy</a>.</p>

<h2>Storage and security</h2>
<p>Data is stored on a private server in the European Union, in a database that keeps each
person's data apart. Connection credentials are stored encrypted. All traffic is encrypted
(HTTPS).</p>

<h2>Retention and deletion</h2>
<p>Data is kept while the person uses arga. They can disconnect Google Health at any time from arga
or from <a href="https://myaccount.google.com/permissions">myaccount.google.com/permissions</a>,
after which arga stops reading anything. They can ask for all their data to be deleted, and it is
deleted.</p>

<h2>Contact</h2>
<p>For any question or to request deletion of your data, write to the support email shown on
Google's authorization screen when connecting arga.</p>"""

STYLE = """<style>
body { font-family: system-ui, sans-serif; line-height: 1.55; max-width: 44rem;
       margin: 0 auto; padding: 2rem 1rem 4rem; }
h1 { font-size: 1.6rem; } h2 { font-size: 1.2rem; margin-top: 2rem; }
hr { margin: 3rem 0; }
</style>"""


def page(request: Request | None) -> str:
    language = words.language(request)
    translated = words.say(request, "privacy.body") if language != "en" else "privacy.body"
    body = (
        ENGLISH
        if translated == "privacy.body"
        else f'{translated}\n\n<hr>\n\n<div lang="en">\n{ENGLISH}\n</div>'
    )
    return f"""<!doctype html>
<html lang="{language}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{words.say(request, "privacy.title")}</title>
{STYLE}
</head>
<body>
{body}
</body>
</html>
"""
