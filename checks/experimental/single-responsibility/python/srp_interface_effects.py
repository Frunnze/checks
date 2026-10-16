AI_PREFIXES = (
    "openai",
    "anthropic",
    "cohere",
    "mistralai",
    "ollama",
    "replicate",
    "litellm",
    "google.generativeai",
    "huggingface_hub",
    "@anthropic-ai/sdk",
    "@google/generative-ai",
)
AI_OPERATIONS = {
    "create",
    "generate",
    "generate_content",
    "complete",
    "completion",
    "acompletion",
    "chat",
    "chat_completion",
    "text_generation",
    "invoke",
    "stream",
    "predict",
    "run",
}


AUTHENTICATION_PREFIXES = (
    "jwt",
    "jose",
    "authlib",
    "oauthlib",
    "bcrypt",
    "passlib",
    "argon2",
    "hmac",
    "cryptography",
    "nacl",
    "jsonwebtoken",
    "bcryptjs",
    "crypto",
    "node:crypto",
)
AUTHENTICATION_OPERATIONS = {
    "encode",
    "decode",
    "hash",
    "verify",
    "checkpw",
    "hashpw",
    "gensalt",
    "sign",
    "new",
    "hexdigest",
    "createHmac",
    "compare",
    "compareSync",
    "hashSync",
}


EMAIL_PREFIXES = (
    "smtplib",
    "aiosmtplib",
    "sendgrid",
    "resend",
    "postmark",
    "nodemailer",
    "@sendgrid/mail",
)
EMAIL_OPERATIONS = {
    "send",
    "sendmail",
    "send_message",
    "sendMail",
    "send_email",
}


PRESENTATION_PREFIXES = (
    "jinja2",
    "django.template",
    "mako",
    "react-dom",
    "react-dom/client",
    "solid-js/web",
    "global.document",
)
PRESENTATION_OPERATIONS = {
    "render",
    "render_to_string",
    "get_template",
    "from_string",
    "createElement",
    "createRoot",
    "hydrate",
    "hydrateRoot",
    "querySelector",
    "querySelectorAll",
    "getElementById",
    "appendChild",
    "write",
    "mount",
}
