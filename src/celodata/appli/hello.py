"""Windows Hello : empreinte, visage ou code confidentiel demandés avant d'ouvrir la table.

C'est une barrière d'accès à l'appli, pas un chiffrement : la table est protégée par le mot de
passe et par le secret de poste. Rien ne sort du poste, Windows fait la vérification lui-même.
"""

import asyncio
import ctypes

# Windows ouvre sa demande derrière la fenêtre d'une appli de bureau : il faut la ramener devant.
_FENETRE_HELLO = "Credential Dialog Xaml Host"
# Sans réponse au bout de ce délai, en secondes, la demande compte comme refusée.
DELAI = 120.0


def _amener_devant() -> bool:
    """Passe la demande de Windows au premier plan. Rend vrai quand c'est fait."""
    user32 = ctypes.WinDLL("user32")
    user32.FindWindowW.restype = ctypes.c_void_p
    user32.GetForegroundWindow.restype = ctypes.c_void_p
    user32.SetForegroundWindow.argtypes = [ctypes.c_void_p]
    fenetre = user32.FindWindowW(_FENETRE_HELLO, None)
    if not fenetre:
        return False
    user32.SetForegroundWindow(fenetre)
    if user32.GetForegroundWindow() != fenetre:
        # Windows refuse le premier plan à un programme qui n'a pas reçu de frappe : une pression
        # sur Alt (0x12), relâchée aussitôt (0x2), lève ce refus.
        user32.keybd_event(0x12, 0, 0, 0)
        user32.keybd_event(0x12, 0, 0x2, 0)
        user32.SetForegroundWindow(fenetre)
    return user32.GetForegroundWindow() == fenetre


async def _suivre() -> None:
    while not _amener_devant():
        await asyncio.sleep(0.2)


def verifier(message: str) -> bool | None:
    """Rend `True` si Windows a reconnu la personne, `False` si elle a refusé, échoué ou n'a pas
    répondu, `None` si le poste n'a pas Windows Hello."""
    try:
        from winrt.windows.security.credentials.ui import (
            UserConsentVerificationResult,
            UserConsentVerifier,
            UserConsentVerifierAvailability,
        )
    except ImportError:
        return None

    async def demander() -> bool | None:
        if await UserConsentVerifier.check_availability_async() != UserConsentVerifierAvailability.AVAILABLE:
            return None
        demande = UserConsentVerifier.request_verification_async(message)
        suivi = asyncio.create_task(_suivre())
        try:
            resultat = await asyncio.wait_for(demande, DELAI)
        except TimeoutError:
            demande.cancel()
            return False
        finally:
            suivi.cancel()
        return resultat == UserConsentVerificationResult.VERIFIED

    try:
        return asyncio.run(demander())
    except OSError:
        return None
