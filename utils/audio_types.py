QUALITY_PROFILES = {
    "standard": {
        "prop_decrease":   0.40,
        "passes":          1,
        "blend_original":  0.25,
        "deepfilter":      False,
        "df_atten_lim_db": 0,
        "rnnoise":         False,
        "afftdn_nf":       -20,
        "voice_boost_db":  1,
        "gate_threshold":  0.012,
        "gate_ratio":      3,
    },
    "enhanced": {
        "prop_decrease":   0.60,
        "passes":          1,
        "blend_original":  0.15,
        "deepfilter":      False,
        "df_atten_lim_db": 0,
        "rnnoise":         True,
        "afftdn_nf":       -25,
        "voice_boost_db":  2,
        "gate_threshold":  0.010,
        "gate_ratio":      4,
    },
    "extreme": {
        "prop_decrease":   0.75,
        "passes":          2,
        "blend_original":  0.15,
        "deepfilter":      True,
        "df_atten_lim_db": 25,
        "rnnoise":         True,
        "afftdn_nf":       -30,
        "voice_boost_db":  3,
        "gate_threshold":  0.008,
        "gate_ratio":      5,
    },
}

PRESET_ALIAS = {
    "light":    "standard",
    "normal":   "enhanced",
    "strong":   "extreme",
    "standard": "standard",
    "enhanced": "enhanced",
    "extreme":  "extreme",
}
DEFAULT_QUALITY = "enhanced"