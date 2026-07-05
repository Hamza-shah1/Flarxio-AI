SUSPICIOUS_KEYWORDS = [
    "login", "signin", "sign-in", "log-in", "logon",
    "verify", "verification", "validate",
    "password", "passwd", "pwd", "reset-password", "password-reset",
    "confirm-account", "account-confirm", "account-update", "update-account",
    "account-suspended", "suspended-account", "authenticate", "auth-required",
    "banking", "secure-banking", "bank-login",
    "free-money", "claim-reward", "prize-winner", "you-won",
    "crypto-giveaway", "bitcoin-free", "eth-giveaway",
    "invoice-payment", "pay-now", "urgent-payment",
    "phish", "phishing", "support-ticket", "helpdesk-alert",
    "unusual-activity", "suspicious-activity",
    "security-alert", "alert-security",
    "delivery-failed", "parcel-held", "track-package",
]

SUSPICIOUS_TLDS = {
    ".tk", ".ml", ".ga", ".cf", ".gq",
    ".xyz", ".top", ".club", ".work",
    ".click", ".link", ".live",
}

PROTECTED_BRANDS = [
    "paypal", "apple", "google", "microsoft", "amazon",
    "facebook", "instagram", "twitter", "netflix", "spotify",
    "dropbox", "linkedin", "github", "discord", "whatsapp",
    "binance", "coinbase", "chase", "wellsfargo", "citibank",
    "bankofamerica", "hsbc", "barclays",
]

HOMOGLYPH_MAP = str.maketrans(
    "ΑΒΕΖΗΙΚΜΝΟΡΤΧαοеосрруух"
    "àáâãäåæçèéêëìíîïðñòóôõöøùúûüýþÿ"
    "ａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ",
    "ABEZHIKMNOPTXaoeocrpyyx"
    "aaaaaaceeeeiiiiðnooooooouuuuypy"
    "abcdefghijklmnopqrstuvwxyz"
)