from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
import os
import requests
import json
import statistics
from dotenv import load_dotenv
from fastapi.responses import RedirectResponse, FileResponse
load_dotenv(override=True)

ML_CLIENT_ID = os.getenv("ML_CLIENT_ID")
ML_CLIENT_SECRET = os.getenv("ML_CLIENT_SECRET")
ML_REDIRECT_URI = os.getenv("ML_REDIRECT_URI")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SECRET_KEY = os.getenv("SUPABASE_SECRET_KEY")

app = FastAPI(
    title="ML Arbitragem Brasil",
    description="Sistema de análise de produtos para Mercado Livre Brasil",
    version="1.0.0"
)
app.mount("/icons", StaticFiles(directory="icons"), name="icons")
def supabase_headers():
    return {
        "apikey": SUPABASE_SECRET_KEY,
        "Authorization": f"Bearer {SUPABASE_SECRET_KEY}",
        "Content-Type": "application/json"
    }


def obtener_tokens_supabase():
    try:
        response = requests.get(
            f"{SUPABASE_URL}/rest/v1/ml_tokens",
            headers=supabase_headers(),
            params={
                "id": "eq.1",
                "select": "access_token,refresh_token,expires_in"
            },
            timeout=20
        )

        if response.status_code != 200:
            return None

        datos = response.json()

        if not datos:
            return None

        return datos[0]

    except Exception:
        return None


def guardar_tokens_supabase(tokens):
    try:
        datos = {
            "id": 1,
            "access_token": tokens.get("access_token"),
            "refresh_token": tokens.get("refresh_token"),
            "expires_in": tokens.get("expires_in")
        }

        response = requests.post(
            f"{SUPABASE_URL}/rest/v1/ml_tokens?on_conflict=id",
            headers={
                **supabase_headers(),
                "Prefer": "resolution=merge-duplicates,return=minimal"
            },
            json=datos,
            timeout=20
        )

        return response.status_code in (200, 201, 204)

    except Exception:
        return False


def renovar_access_token():
    try:
        tokens = obtener_tokens_supabase()

        if not tokens:
            return None

        refresh_token = tokens.get("refresh_token")

        if not refresh_token:
            return None

        response = requests.post(
            "https://api.mercadolibre.com/oauth/token",
            data={
                "grant_type": "refresh_token",
                "client_id": ML_CLIENT_ID,
                "client_secret": ML_CLIENT_SECRET,
                "refresh_token": refresh_token
            },
            timeout=20
        )

        if response.status_code != 200:
            return None

        nuevos_tokens = response.json()

        if not guardar_tokens_supabase(nuevos_tokens):
            return None

        return nuevos_tokens.get("access_token")

    except Exception:
        return None

@app.get("/")
def inicio():
    return FileResponse("index.html")

@app.get("/manifest.json")
def manifest():
    return FileResponse("manifest.json", media_type="application/manifest+json")

@app.get("/service-worker.js")
def service_worker():
    return FileResponse("service-worker.js", media_type="application/javascript")
@app.get("/login")
def login():
    auth_url = (
        "https://auth.mercadolivre.com.br/authorization"
        "?response_type=code"
        f"&client_id={ML_CLIENT_ID}"
        f"&redirect_uri={ML_REDIRECT_URI}"
    )

    return RedirectResponse(url=auth_url)

@app.get("/callback")
def callback(code: str | None = None):
    if not code:
        return {
            "status": "error",
            "mensaje": "No se recibió código de autorización"
        }

    token_url = "https://api.mercadolibre.com/oauth/token"

    data = {
        "grant_type": "authorization_code",
        "client_id": ML_CLIENT_ID,
        "client_secret": ML_CLIENT_SECRET,
        "code": code,
        "redirect_uri": ML_REDIRECT_URI
    }

    response = requests.post(token_url, data=data)

    if response.status_code != 200:
        return {
            "status": "error",
            "codigo_http": response.status_code
        }

    token_data = response.json()

    if not guardar_tokens_supabase(token_data):
        return {
        "status": "error",
        "mensaje": "No fue posible guardar los tokens en Supabase"
    }

    return {
        "status": "conectado",
        "user_id": token_data.get("user_id"),
        "expires_in": token_data.get("expires_in")
    }
@app.get("/me")
def me():

    tokens = obtener_tokens_supabase()

    if not tokens:
            return {
                "status": "error",
                "mensaje": "No hay tokens guardados en Supabase"
    }
    access_token = tokens.get("access_token")

    if not access_token:
        return {
            "status": "error",
            "mensaje": "No hay access_token guardado"
        }

    response = requests.get(
        "https://api.mercadolibre.com/users/me",
        headers={
            "Authorization": f"Bearer {access_token}"
        }
    )

    if response.status_code == 401:
        access_token = renovar_access_token()

        if not access_token:
            return {
                "status": "error",
                "mensaje": "No fue posible renovar el access_token"
        }

    response = requests.get(
        "https://api.mercadolibre.com/users/me",
        headers={
            "Authorization": f"Bearer {access_token}"
        }
    )

    if response.status_code == 401:
        access_token = renovar_access_token()

        if not access_token:
            return {
                "status": "error",
                "mensaje": "No fue posible renovar el access_token"
            }

        response = requests.get(
            "https://api.mercadolibre.com/users/me",
            headers={
                "Authorization": f"Bearer {access_token}"
            }
        )

    if response.status_code != 200:
        return {
            "status": "error",
            "codigo_http": response.status_code
        }

    data = response.json()

    return {
        "status": "ok",
        "id": data.get("id"),
        "nickname": data.get("nickname"),
        "site_id": data.get("site_id")
    }
@app.get("/ean/{ean}")
def buscar_ean(ean: str):
    tokens = obtener_tokens_supabase()

    if not tokens:
     return {
        "status": "error",
        "mensaje": "No hay tokens guardados en Supabase"
    }

    access_token = tokens.get("access_token")

    if not access_token:
        return {
            "status": "error",
            "mensaje": "No hay access_token guardado"
        }

    response = requests.get(
        "https://api.mercadolibre.com/products/search",
        headers={
            "Authorization": f"Bearer {access_token}"
        },
        params={
            "status": "active",
            "site_id": "MLB",
            "product_identifier": ean
        },
        timeout=20
    )

    if response.status_code != 200:
        return {
            "status": "error",
            "codigo_http": response.status_code
        }

    data = response.json()

    resultados = data.get("results", [])

    if not resultados:
        return {
            "status": "ok",
            "ean": ean,
            "encontrado": False,
            "mensaje": "Producto no encontrado en Mercado Livre"
        }

    producto = resultados[0]

    return {
        "status": "ok",
        "ean": ean,
                "encontrado": True,
        "producto": {
            "product_id": producto.get("id"),
            "nombre": producto.get("name"),
            "dominio": producto.get("domain_id"),
            "catalog_product_id": producto.get("catalog_product_id")
        }
    }
@app.get("/competencia/{product_id}")
def competencia(product_id: str):

    tokens = obtener_tokens_supabase()

    if not tokens:
        return {
            "status": "error",
            "mensaje": "No hay tokens guardados en Supabase"
    }

    access_token = tokens.get("access_token")

    if not access_token:
        return {
            "status": "error",
            "mensaje": "No hay access_token guardado"
        }

    response = requests.get(
        f"https://api.mercadolibre.com/products/{product_id}/items",
        headers={
            "Authorization": f"Bearer {access_token}"
        },
        timeout=20
    )

    if response.status_code != 200:
        return {
            "status": "error",
            "codigo_http": response.status_code
        }

    data = response.json()

    resultados = data.get("results", [])

    competidores = []

    for item in resultados:
        competidores.append({
            "item_id": item.get("item_id"),
            "seller_id": item.get("seller_id"),
            "precio": item.get("price"),
            "moneda": item.get("currency_id"),
            "condicion": item.get("condition"),
            "ventas_visibles": item.get("sold_quantity")
        })

    precios = [
        item["precio"]
        for item in competidores
        if isinstance(item["precio"], (int, float))
    ]

    return {
        "status": "ok",
        "product_id": product_id,
        "total_publicaciones": data.get("paging", {}).get("total", 0),
        "precio_minimo": min(precios) if precios else None,
        "precio_maximo": max(precios) if precios else None,
        "precio_promedio": round(sum(precios) / len(precios), 2) if precios else None,
        "competidores": competidores
    }
@app.get("/analisis")
def analisis(
    precio_venta: float,
    precio_compra: float,
    comision_pct: float = 16,
    otros_costos: float = 0,
    roi_objetivo: float = 30
):
    comision = precio_venta * (comision_pct / 100)

    ganancia = (
        precio_venta
        - precio_compra
        - comision
        - otros_costos
    )

    roi = (
        ganancia / precio_compra * 100
        if precio_compra > 0
        else 0
    )

    margen = (
        ganancia / precio_venta * 100
        if precio_venta > 0
        else 0
    )
    costo_maximo = (
        (precio_venta - comision - otros_costos)
        / (1 + roi_objetivo / 100)
        if precio_venta > 0
        else 0
    )
    if roi >= roi_objetivo:
        semaforo = "COMPRAR"
    elif roi >= (roi_objetivo - 10):
        semaforo = "ANALIZAR"
    else:
        semaforo = "NO COMPRAR"
    return {
        "precio_venta": round(precio_venta, 2),
        "precio_compra": round(precio_compra, 2),
        "comision": round(comision, 2),
        "otros_costos": round(otros_costos, 2),
        "ganancia": round(ganancia, 2),
        "roi": round(roi, 2),
        "margen": round(margen, 2),
"roi_objetivo": round(roi_objetivo, 2),
"costo_maximo": round(costo_maximo, 2),
    "semaforo": semaforo}
@app.get("/analisis-ean/{ean}")
def analisis_ean(
    ean: str,
    precio_compra: float,
    listing_type_id: str = "gold_special",
        tipo_envio: str = "gratis",
    otros_costos: float = 0,
    roi_objetivo: float = 30
):
    tokens = obtener_tokens_supabase()

    if not tokens:
        return {
        "status": "error",
        "mensaje": "No hay tokens guardados en Supabase"
    }

    access_token = tokens.get("access_token")

    if not access_token:
        return {
            "status": "error",
            "mensaje": "No hay access_token guardado"
        }

    response_producto = requests.get(
        "https://api.mercadolibre.com/products/search",
        headers={
            "Authorization": f"Bearer {access_token}"
        },
        params={
            "status": "active",
            "site_id": "MLB",
            "product_identifier": ean
        },
        timeout=20
    )
    if response_producto.status_code == 401:
        access_token = renovar_access_token()

        if not access_token:
            return {
                "status": "error",
                "message": "No fue posible renovar el token de Mercado Livre"
            }

        response_producto = requests.get(
            "https://api.mercadolibre.com/products/search",
            headers={
                "Authorization": f"Bearer {access_token}"
            },
            params={
                "status": "active",
                "site_id": "MLB",
                "product_identifier": ean
            },
            timeout=20
        )
    if response_producto.status_code == 404:
        resultados_producto = []

    elif response_producto.status_code != 200:
        return {
            "status": "error",
            "codigo_http": response_producto.status_code
    }

    else:
        data_producto = response_producto.json()
        resultados_producto = data_producto.get("results", [])

    if not resultados_producto:
        response_alternativa = requests.get(
        "https://api.mercadolibre.com/sites/MLB/search",
        headers={
            "Authorization": f"Bearer {access_token}"
        },
        params={
            "q": ean,
            "limit": 10
        },
        timeout=20
    )

        if response_alternativa.status_code == 200:
            data_alternativa = response_alternativa.json()
            items_alternativos = data_alternativa.get("results", [])

            if items_alternativos:
                return {
                    "status": "alternativo",
                    "ean": ean,
                    "encontrado": False,
                    "mensaje": "EAN no encontrado en catálogo, pero existen publicaciones relacionadas",
                    "publicaciones_alternativas": len(items_alternativos)
                }

        return {
            "status": "ok",
            "ean": ean,
            "encontrado": False
        }

    producto = resultados_producto[0]
    product_id = producto.get("id")
    print("PRODUCT ID EAN:", ean, "PRODUCT_ID:", product_id)

    print("PRODUCTO COMPLETO:", producto)
    print("DOMAIN ID EAN:", ean, "DOMAIN_ID:", producto.get("domain_id"))
    domain_id = producto.get("domain_id")
    category_id = producto.get("category_id")

    if not category_id and domain_id:
        response_categorias = requests.get(
        f"https://api.mercadolibre.com/catalog_domains/{domain_id}/categories",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=20
    )

    print("DOMAIN CATEGORIES STATUS:", response_categorias.status_code)
    print("DOMAIN CATEGORIES DATA:", response_categorias.text)
    if response_categorias.status_code == 200:
        categorias_domain = response_categorias.json()

    if categorias_domain:
        category_id = categorias_domain[0].get("id")
        print("CATEGORY ID DESDE DOMAIN:", category_id)
    print("CATEGORIA ML EAN:", ean, "CATEGORY_ID:", category_id)
    ranking = None

    response_ranking = requests.get(
        f"https://api.mercadolibre.com/highlights/MLB/product/{product_id}",
        headers={
            "Authorization": f"Bearer {access_token}"
        },
        timeout=20
    )

    if response_ranking.status_code == 200:
        data_ranking = response_ranking.json()
        ranking = data_ranking.get("position")
    response_competencia = requests.get(
        f"https://api.mercadolibre.com/products/{product_id}/items",
        headers={
            "Authorization": f"Bearer {access_token}"
        },
        timeout=20
    )

    if response_competencia.status_code == 404:
        resultados = []

    elif response_competencia.status_code != 200:
        return {
            "status": "error",
            "codigo_http": response_competencia.status_code
    }

    else:
        data_competencia = response_competencia.json()
        resultados = data_competencia.get("results", [])
    item_id_referencia = None
    response_precios = None
    if resultados:
     item_id_referencia = resultados[0].get("item_id")
     print("ITEM ID REFERENCIA:", item_id_referencia)
    precios = [
        item.get("price")
        for item in resultados
        if isinstance(item.get("price"), (int, float))
    ]
    

    if not precios:
        response_precios = requests.get(
        "https://api.mercadolibre.com/sites/MLB/search",
        headers={
            "Authorization": f"Bearer {access_token}"
        },
        params={
            "q": ean,
            "limit": 20
        },
        timeout=20
    )
    
    if response_precios is not None and response_precios.status_code == 200:
        data_precios = response_precios.json()
        publicaciones = data_precios.get("results", [])

        precios = [
            item.get("price")
            for item in publicaciones
            if isinstance(item.get("price"), (int, float))
        ]

        if publicaciones and not item_id_referencia:
            item_id_referencia = publicaciones[0].get("id")

    if not category_id and item_id_referencia:
        response_item = requests.get(
            f"https://api.mercadolibre.com/items/{item_id_referencia}",
            headers={
                "Authorization": f"Bearer {access_token}"
            },
            timeout=20
        )
        print("ITEM STATUS:", response_item.status_code)
        print("ITEM DATA:", response_item.text)

        if response_item.status_code == 200:
            data_item = response_item.json()
            category_id = data_item.get("category_id")
            print(
                "CATEGORIA ITEM EAN:",
                ean,
                "ITEM:",
                item_id_referencia,
                "CATEGORY_ID:",
                category_id
            )

    if not precios:
        return {
        "status": "sin_precio",
        "ean": ean,
        "producto": producto.get("name"),
        "product_id": product_id,
        "total_publicaciones": len(resultados),
        "ranking": ranking,
        "mensaje": "Producto encontrado, pero no hay precios activos disponibles en Mercado Livre"
    }
    
    precio_minimo = min(precios)
    precio_promedio = sum(precios) / len(precios)
    cantidad_precios = len(precios)
    precio_mediana = statistics.median(precios)

    if cantidad_precios <= 2:
        precio_recomendado = precio_minimo
    elif cantidad_precios <= 5:
        precio_recomendado = min(precio_mediana, precio_minimo * 1.10)
    else:
        precio_recomendado = precio_mediana

    precio_venta = round(precio_recomendado, 2)
    print("TARIFA EAN:", ean, "CATEGORY_ID:", category_id, "PRECIO:", precio_venta, "LISTING:", listing_type_id)
    response_tarifa = requests.get(
    "https://api.mercadolibre.com/sites/MLB/listing_prices",
    headers={
        "Authorization": f"Bearer {access_token}"
    },
    params={
        "price": precio_venta,
        "currency_id": "BRL",
        "catalog_product_id": product_id,
        "listing_type_id": listing_type_id,
    },
    timeout=20
)
    print("TARIFA STATUS:", response_tarifa.status_code)
    print("TARIFA RESPUESTA:", response_tarifa.text)
    if response_tarifa.status_code == 200:
        data_tarifa = response_tarifa.json()

        if isinstance(data_tarifa, list) and len(data_tarifa) > 0:
            comision = float(data_tarifa[0].get("sale_fee_amount", 0))
        elif isinstance(data_tarifa, dict):
            comision = float(data_tarifa.get("sale_fee_amount", 0))
        else:
            comision = 0
    else:
            comision = 0
    response_envio = requests.get(
        f"https://api.mercadolibre.com/users/515849137/shipping_options/free",
        headers={
            "Authorization": f"Bearer {access_token}"
        },
        params={"item_id": item_id_referencia,
            "item_price": precio_venta,
            "category_id": category_id,
            "listing_type_id": listing_type_id,
            "mode": "me2",
            "condition": "new",
            "logistic_type": "drop_off",
            "free_shipping": "true",
            "verbose": "true"
        },
        timeout=20
    )           
           
    costo_envio = 0
    
    if tipo_envio == "gratis" and response_envio.status_code == 200:
        data_envio = response_envio.json()
        cobertura = data_envio.get("coverage", {})
        todo_brasil = cobertura.get("all_country", {})
        costo_envio = float(todo_brasil.get("list_cost", 0))

    
    
    

    ganancia = (
        precio_venta
        - precio_compra
        - comision
        - costo_envio
        - otros_costos
    )

    roi = (
        ganancia / precio_compra * 100
        if precio_compra > 0
        else 0
    )

    margen = (
        ganancia / precio_venta * 100
        if precio_venta > 0
        else 0
    )
    costo_maximo = (
        (precio_venta - comision - costo_envio - otros_costos)
        / (1 + roi_objetivo / 100)
        if precio_venta > 0
        else 0
    )
    if costo_maximo < 0:
        costo_maximo = 0

    if roi >= roi_objetivo:
        semaforo = "COMPRAR"
    elif roi >= (roi_objetivo - 10):
        semaforo = "ANALIZAR"
    else:
        semaforo = "NO COMPRAR"

    return {
        "status": "ok",
        "ean": ean,
        "producto": producto.get("name"),
        "product_id": product_id,
        "total_publicaciones": len(resultados),
        "ranking": ranking,
        "precio_minimo_competencia": round(precio_minimo, 2),
        "precio_promedio_competencia": round(precio_promedio, 2),
        "precio_recomendado": round(precio_recomendado, 2),
        "precio_venta_referencia": precio_venta,
        "precio_compra": round(precio_compra, 2),
        "comision": round(comision, 2),
        "costo_envio": round(costo_envio, 2),
        "otros_costos": round(otros_costos, 2),
        "ganancia": round(ganancia, 2),
        "roi": round(roi, 2),
        "margen": round(margen, 2),
        "roi_objetivo": round(roi_objetivo, 2),
        "costo_maximo": round(costo_maximo, 2),
        "semaforo": semaforo
    }
@app.get("/item/{item_id}")
def detalle_item(item_id: str):
    tokens = obtener_tokens_supabase()

    if not tokens:
        return {
        "status": "error",
        "mensaje": "No hay tokens guardados en Supabase"
    }
    access_token = tokens.get("access_token")

    if not access_token:
        return {
            "status": "error",
            "mensaje": "No hay access_token guardado"
        }

    response = requests.get(
        f"https://api.mercadolibre.com/items/{item_id}",
        headers={
            "Authorization": f"Bearer {access_token}"
        },
        timeout=20
    )

    if response.status_code != 200:
        return {
            "status": "error",
            "codigo_http": response.status_code
        }

    data = response.json()

    return {
        "status": "ok",
        "item_id": data.get("id"),
        "titulo": data.get("title"),
        "sold_quantity": data.get("sold_quantity")
    }
@app.post("/notifications")
async def notifications(request: Request):
    data = await request.json()
    print("Notificacion recibida:", data)

    return {
        "status": "ok"
    }