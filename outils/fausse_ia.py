"""Une fausse IA, pour essayer la passerelle sans rien envoyer à l'extérieur.

Elle écoute sur cette machine seulement, affiche ce qu'elle reçoit (donc ce qu'une vraie IA verrait)
et répond en répétant le dernier message.

    uv run --extra passerelle python outils/fausse_ia.py
"""

import json

import uvicorn
from starlette.applications import Starlette
from starlette.responses import JSONResponse, StreamingResponse
from starlette.routing import Route

PORT = 8799


async def discussion(request):
    corps = await request.json()
    dernier = corps["messages"][-1]["content"]
    texte = dernier if isinstance(dernier, str) else " ".join(p.get("text", "") for p in dernier)
    print("\n" + "=" * 70)
    print("CE QUE L'IA REÇOIT :")
    print("=" * 70)
    for message in corps["messages"]:
        print(f"[{message.get('role')}] {message.get('content')}", flush=True)
    # La passerelle remplace la clé de l'utilisateur par celle de l'entreprise.
    print("(clé d'un utilisateur Celodata reçue : " + ("OUI, anormal" if "celo-" in request.headers.get("authorization", "") else "non") + ")", flush=True)
    reponse = "J'ai bien lu votre message. Le voici, répété :\n\n" + texte
    if not corps.get("stream"):
        return JSONResponse({"choices": [{"index": 0, "message": {"role": "assistant", "content": reponse}}]})

    async def flux():
        # Morceaux de 3 caractères : presque tous les jetons arrivent coupés.
        for i in range(0, len(reponse), 3):
            morceau = {"choices": [{"index": 0, "delta": {"content": reponse[i : i + 3]}, "finish_reason": None}]}
            yield f"data: {json.dumps(morceau)}\n\n"
        yield 'data: {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}\n\n'
        yield "data: [DONE]\n\n"

    return StreamingResponse(flux(), media_type="text/event-stream")


async def modeles(request):
    return JSONResponse({"data": [{"id": "fausse-ia"}]})


appli = Starlette(
    routes=[
        Route("/v1/chat/completions", discussion, methods=["POST"]),
        Route("/v1/models", modeles, methods=["GET"]),
    ]
)

if __name__ == "__main__":
    print(f"Fausse IA sur http://127.0.0.1:{PORT}/v1 (Ctrl+C pour arrêter)")
    uvicorn.run(appli, host="127.0.0.1", port=PORT, log_level="warning")
