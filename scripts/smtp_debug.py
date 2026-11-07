import smtplib
from agent.config import settings
print("host", settings.smtp_host, "| port", settings.smtp_port, "| user", settings.smtp_user,
      "| to", settings.alert_email_to, "| password length", len(settings.smtp_password or ""))
s = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15)
s.set_debuglevel(1)
s.ehlo(); s.starttls(); s.ehlo()
s.login(settings.smtp_user, settings.smtp_password)
print("LOGIN OK")
s.quit()
