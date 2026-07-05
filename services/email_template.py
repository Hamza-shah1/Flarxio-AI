# email_template.py

def password_reset_email(reset_link: str) -> str:
    return f"""
<!DOCTYPE html>
<html>
<body style="margin:0;padding:0;background:#0d0d1a;font-family:'Segoe UI',Arial,sans-serif;">

<table width="100%" cellpadding="0" cellspacing="0" style="background:#0d0d1a;padding:30px 0;">
  <tr>
    <td align="center">

      <table width="520" cellpadding="0" cellspacing="0"
        style="background:#12122a;border-radius:12px;
               border:1px solid #2a2a4a;
               overflow:hidden;">

        <!-- Header -->
        <tr>
          <td style="background:linear-gradient(135deg,#3b1fa3,#1a8fd1);padding:24px;text-align:center;">
            <span style="font-size:24px;font-weight:bold;color:#ffffff;letter-spacing:1px;">
              Flarixo AI
            </span>
            <br>
            <span style="font-size:11px;color:#a8d8f0;letter-spacing:3px;text-transform:uppercase;">
              The AI Toolkit
            </span>
          </td>
        </tr>

        <!-- Body -->
        <tr>
          <td style="padding:32px;color:#b0b8d0;">

            <h2 style="margin-top:0;color:#ffffff;text-align:center;">Reset Your Password</h2>

            <p style="font-size:15px;line-height:1.6;">
              You requested to reset your password for your <b style="color:#38bdf8;">Flarixo AI</b> account.
              Click the button below to create a new password.
            </p>

            <div style="text-align:center;margin:30px 0;">
              <a href="{reset_link}"
                 style="
                    display:inline-block;
                    padding:14px 30px;
                    background:linear-gradient(135deg,#3b1fa3,#1a8fd1);
                    color:#ffffff;
                    text-decoration:none;
                    font-weight:bold;
                    border-radius:8px;
                 ">
                Reset Password
              </a>
            </div>

            <p style="font-size:14px;">
              This link will expire in <b style="color:#38bdf8;">15 minutes</b>.
            </p>

            <p style="font-size:14px;">
              If you did not request this password reset, you can safely ignore this email.
            </p>

          </td>
        </tr>

        <!-- Footer -->
        <tr>
          <td style="background:#0a0a1a;padding:18px;text-align:center;
                     font-size:12px;color:#555e7a;border-top:1px solid #2a2a4a;">
            &copy; 2025 <b style="color:#7c86a8;">Flarixo AI</b>. All rights reserved.<br>
            This is an automated email. Please do not reply.
          </td>
        </tr>

      </table>

    </td>
  </tr>
</table>

</body>
</html>
"""


def contact_email(*, name: str, email: str, message: str) -> str:
    """Premium Flarixo AI Contact Email Template"""

    safe_name = (
        name.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )

    safe_email = (
        email.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )

    safe_message = (
        message.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\n", "<br>")
    )

    return f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Flarixo AI Contact</title>
</head>

<body style="
    margin:0;
    padding:0;
    background:#050816;
    font-family:Segoe UI,Arial,sans-serif;
">

<table width="100%" cellpadding="0" cellspacing="0" style="background:#050816;padding:40px 20px;">
<tr>
<td align="center">

<table width="650" cellpadding="0" cellspacing="0"
style="
    background:#0b1020;
    border:1px solid rgba(255,255,255,.08);
    border-radius:24px;
    overflow:hidden;
">

    <!-- Header -->
    <tr>
        <td align="center"
        style="
            background:linear-gradient(135deg,#7c3aed,#3b82f6);
            padding:35px 20px;
        ">
            <div style="
                font-size:34px;
                font-weight:800;
                color:#ffffff;
                letter-spacing:.5px;
            ">
                Flarixo AI
            </div>

            <div style="
                margin-top:8px;
                color:rgba(255,255,255,.9);
                font-size:14px;
                letter-spacing:1px;
            ">
                NEW CONTACT FORM SUBMISSION
            </div>
        </td>
    </tr>

    <!-- Badge -->
    <tr>
        <td align="center" style="padding-top:30px;">
            <span style="
                background:rgba(124,58,237,.15);
                color:#a78bfa;
                border:1px solid rgba(167,139,250,.25);
                padding:10px 18px;
                border-radius:999px;
                font-size:12px;
                font-weight:700;
                letter-spacing:.5px;
            ">
                ✨ CUSTOMER MESSAGE RECEIVED
            </span>
        </td>
    </tr>

    <!-- Title -->
    <tr>
        <td align="center" style="padding:25px 40px 10px;">
            <div style="
                color:#ffffff;
                font-size:28px;
                font-weight:700;
            ">
                Someone contacted Flarixo AI
            </div>
        </td>
    </tr>

    <!-- Subtitle -->
    <tr>
        <td align="center" style="padding:0 50px 30px;">
            <div style="
                color:#94a3b8;
                font-size:15px;
                line-height:1.8;
            ">
                A new message has been submitted through your website contact form.
            </div>
        </td>
    </tr>

    <!-- Info Card -->
    <tr>
        <td style="padding:0 35px;">
            <table width="100%" cellpadding="0" cellspacing="0"
            style="
                background:#111827;
                border:1px solid rgba(255,255,255,.08);
                border-radius:18px;
            ">

                <tr>
                    <td style="padding:22px 25px;border-bottom:1px solid rgba(255,255,255,.08);">
                        <div style="color:#64748b;font-size:12px;font-weight:700;">
                            NAME
                        </div>
                        <div style="margin-top:6px;color:#ffffff;font-size:17px;">
                            {safe_name}
                        </div>
                    </td>
                </tr>

                <tr>
                    <td style="padding:22px 25px;border-bottom:1px solid rgba(255,255,255,.08);">
                        <div style="color:#64748b;font-size:12px;font-weight:700;">
                            EMAIL
                        </div>
                        <div style="margin-top:6px;">
                            <a href="mailto:{safe_email}"
                            style="
                                color:#60a5fa;
                                text-decoration:none;
                                font-size:17px;
                            ">
                                {safe_email}
                            </a>
                        </div>
                    </td>
                </tr>

                <tr>
                    <td style="padding:22px 25px;">
                        <div style="color:#64748b;font-size:12px;font-weight:700;">
                            MESSAGE
                        </div>

                        <div style="
                            margin-top:15px;
                            background:#0f172a;
                            border-left:4px solid #3b82f6;
                            border-radius:12px;
                            padding:20px;
                            color:#e2e8f0;
                            line-height:1.8;
                            font-size:15px;
                        ">
                            {safe_message}
                        </div>
                    </td>
                </tr>

            </table>
        </td>
    </tr>

    <!-- CTA -->
    <tr>
        <td align="center" style="padding:35px;">
            <a href="mailto:{safe_email}"
            style="
                display:inline-block;
                background:linear-gradient(135deg,#7c3aed,#3b82f6);
                color:#ffffff;
                text-decoration:none;
                padding:15px 30px;
                border-radius:12px;
                font-weight:700;
                font-size:14px;
            ">
                Reply to Customer →
            </a>
        </td>
    </tr>

    <!-- Footer -->
    <tr>
        <td align="center"
        style="
            padding:25px;
            border-top:1px solid rgba(255,255,255,.08);
            color:#64748b;
            font-size:12px;
        ">
            © Flarixo AI • Premium AI Tools Platform<br>
            This email was automatically generated from the website contact form.
        </td>
    </tr>

</table>

</td>
</tr>
</table>

</body>
</html>
"""