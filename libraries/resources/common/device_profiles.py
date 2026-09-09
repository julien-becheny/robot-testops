"""
Catalogue de profils d'appareils pour l'emulation Playwright (Browser library).

Enrichit l'ancien « viewport seul » avec un vrai profil : user-agent, densite
d'ecran (deviceScaleFactor), tactile (hasTouch) et flag mobile (isMobile). Ces
options rendent l'emulation credible : media queries mobiles (`pointer: coarse`),
sites qui adaptent selon l'user-agent, evenements tactiles.

Limites (fiabilite) :
- `isMobile` et `hasTouch` ne sont PAS supportes par Firefox dans Playwright :
  on ne les applique que pour chromium/webkit (sinon erreur au lancement).
- L'emulation reste une approximation d'un moteur desktop. Pour une validation
  finale mobile (iOS/Safari reel, appli native installee), utiliser de VRAIS
  appareils (Appium / device cloud) — l'emulation ne les remplace pas.

Les viewports historiques (desktop/tablet/mobile) sont conserves pour ne pas
changer les attentes de mise en page ; seuls UA / densite / tactile sont ajoutes.
"""

_IPHONE_UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
              "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 "
              "Mobile/15E148 Safari/604.1")
_IPAD_UA = ("Mozilla/5.0 (iPad; CPU OS 16_0 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 "
            "Mobile/15E148 Safari/604.1")

# Profil par label d'appareil (tel que fourni par TestOps : desktop|tablet|mobile).
DEVICE_PROFILES = {
    "desktop": {
        "width": 1920, "height": 1080, "user_agent": None,
        "device_scale_factor": 1, "is_mobile": False, "has_touch": False,
    },
    "tablet": {
        "width": 768, "height": 1024, "user_agent": _IPAD_UA,
        "device_scale_factor": 2, "is_mobile": True, "has_touch": True,
    },
    "mobile": {
        "width": 375, "height": 812, "user_agent": _IPHONE_UA,
        "device_scale_factor": 3, "is_mobile": True, "has_touch": True,
    },
}

# Moteurs qui acceptent isMobile / hasTouch (Firefox ne les supporte pas).
_TOUCH_CAPABLE = ("chromium", "webkit")


def get_new_context_kwargs(browser, device):
    """Construit les arguments `New Context` (Browser library) pour un couple
    (navigateur, appareil), en respectant les limites de chaque moteur.

    A etaler tel quel : `New Context  &{Ctx_Kwargs}`.

    Args:
        browser: chromium | firefox | webkit
        device:  desktop | tablet | mobile

    Returns:
        dict des arguments New Context (viewport toujours present ; userAgent /
        deviceScaleFactor si definis ; isMobile / hasTouch seulement si le moteur
        les supporte).
    """
    profile = DEVICE_PROFILES.get(str(device).lower(), DEVICE_PROFILES["desktop"])
    kwargs = {"viewport": {"width": profile["width"], "height": profile["height"]}}
    if profile.get("user_agent"):
        kwargs["userAgent"] = profile["user_agent"]
    if profile.get("device_scale_factor"):
        kwargs["deviceScaleFactor"] = float(profile["device_scale_factor"])
    if str(browser).lower() in _TOUCH_CAPABLE:
        if profile.get("is_mobile"):
            kwargs["isMobile"] = True
        if profile.get("has_touch"):
            kwargs["hasTouch"] = True
    return kwargs
