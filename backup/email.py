"""
Email notification service
Sends payday notifications to employees when a payroll run completes.
Uses Python's built-in smtplib — no external API needed.

Configure SMTP in .env:
  SMTP_HOST=smtp.sendgrid.net
  SMTP_PORT=587
  SMTP_USER=apikey
  SMTP_PASSWORD=your-key
  FROM_EMAIL=payroll@yourcompany.com
"""
import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from typing import Optional


SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
FROM_EMAIL = os.getenv("FROM_EMAIL", "payroll@company.com")


def _send(to: str, subject: str, html_body: str, pdf_path: Optional[str] = None) -> bool:
    """Send an email. Returns True on success, False on failure."""
    if not SMTP_HOST or not SMTP_USER:
        print(f"[email] SMTP not configured — skipping email to {to}")
        return False

    msg = MIMEMultipart("mixed")
    msg["From"] = FROM_EMAIL
    msg["To"] = to
    msg["Subject"] = subject

    msg.attach(MIMEText(html_body, "html"))

    if pdf_path and os.path.exists(pdf_path):
        with open(pdf_path, "rb") as f:
            part = MIMEApplication(f.read(), Name=os.path.basename(pdf_path))
            part["Content-Disposition"] = f'attachment; filename="{os.path.basename(pdf_path)}"'
            msg.attach(part)

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(FROM_EMAIL, to, msg.as_string())
        return True
    except Exception as e:
        print(f"[email] Failed to send to {to}: {e}")
        return False


def send_paystub_notification(
    employee_email: str,
    employee_name: str,
    company_name: str,
    pay_date: str,
    net_pay: float,
    pdf_path: Optional[str] = None,
) -> bool:
    """Notify an employee that their paystub is ready."""
    subject = f"Your paystub is ready — {company_name} ({pay_date})"
    html = f"""
    <div style="font-family:sans-serif;max-width:520px;margin:0 auto">
      <div style="background:#1a1a1a;padding:20px 24px;border-radius:8px 8px 0 0">
        <h2 style="color:#fff;margin:0;font-size:18px">{company_name}</h2>
        <p style="color:#aaa;margin:4px 0 0;font-size:13px">Payroll notification</p>
      </div>
      <div style="padding:24px;border:1px solid #e0e0e0;border-top:none;border-radius:0 0 8px 8px">
        <p style="font-size:15px">Hi {employee_name},</p>
        <p>Your paystub for <strong>{pay_date}</strong> is ready.</p>
        <div style="background:#f5f5f5;padding:16px;border-radius:6px;margin:16px 0">
          <p style="margin:0;font-size:13px;color:#666">Net pay</p>
          <p style="margin:4px 0 0;font-size:28px;font-weight:600;color:#1a7a3c">
            ${net_pay:,.2f}
          </p>
        </div>
        {"<p>Your paystub PDF is attached to this email.</p>" if pdf_path else ""}
        <p style="font-size:12px;color:#888;margin-top:24px">
          This is an automated message from your payroll system.
          Please contact HR if you have questions about your pay.
        </p>
      </div>
    </div>
    """
    return _send(employee_email, subject, html, pdf_path)


def send_payroll_complete_notification(
    admin_email: str,
    company_name: str,
    pay_period: str,
    employee_count: int,
    total_gross: float,
    total_net: float,
    pay_run_id: str,
) -> bool:
    """Notify payroll admin that a run completed successfully."""
    subject = f"Payroll complete — {pay_period} ({company_name})"
    html = f"""
    <div style="font-family:sans-serif;max-width:520px;margin:0 auto">
      <div style="background:#1a1a1a;padding:20px 24px;border-radius:8px 8px 0 0">
        <h2 style="color:#fff;margin:0;font-size:18px">Payroll Complete ✓</h2>
        <p style="color:#aaa;margin:4px 0 0;font-size:13px">{company_name}</p>
      </div>
      <div style="padding:24px;border:1px solid #e0e0e0;border-top:none;border-radius:0 0 8px 8px">
        <p>Your payroll run for <strong>{pay_period}</strong> completed successfully.</p>
        <table style="width:100%;border-collapse:collapse;font-size:14px">
          <tr><td style="padding:6px 0;color:#666">Employees paid</td><td style="text-align:right;font-weight:500">{employee_count}</td></tr>
          <tr><td style="padding:6px 0;color:#666">Total gross</td><td style="text-align:right;font-weight:500">${total_gross:,.2f}</td></tr>
          <tr style="border-top:1px solid #eee"><td style="padding:8px 0;font-weight:600">Total net paid</td><td style="text-align:right;font-weight:600;color:#1a7a3c;font-size:16px">${total_net:,.2f}</td></tr>
        </table>
        <p style="font-size:12px;color:#888;margin-top:16px">
          Pay run ID: {pay_run_id}<br>
          Paystub PDFs have been generated and employees will be notified.
        </p>
      </div>
    </div>
    """
    return _send(admin_email, subject, html)


def send_password_reset(email: str, reset_token: str, company_name: str) -> bool:
    """Send password reset link."""
    reset_url = f"{os.getenv('FRONTEND_URL', 'http://localhost:3000')}/reset-password?token={reset_token}"
    subject = f"Password reset — {company_name}"
    html = f"""
    <div style="font-family:sans-serif;max-width:460px;margin:0 auto">
      <div style="background:#1a1a1a;padding:20px 24px;border-radius:8px 8px 0 0">
        <h2 style="color:#fff;margin:0;font-size:18px">Password reset</h2>
      </div>
      <div style="padding:24px;border:1px solid #e0e0e0;border-top:none;border-radius:0 0 8px 8px">
        <p>Click the button below to reset your password. This link expires in 1 hour.</p>
        <a href="{reset_url}" style="display:inline-block;margin:16px 0;padding:12px 24px;
           background:#1a1a1a;color:#fff;text-decoration:none;border-radius:6px;font-weight:500">
          Reset password
        </a>
        <p style="font-size:12px;color:#888">
          If you did not request this reset, ignore this email. Your password will not change.
        </p>
      </div>
    </div>
    """
    return _send(email, subject, html)
