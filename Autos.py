import requests
from bs4 import BeautifulSoup
import re
import pandas as pd
import inquirer
import unicodedata
import openpyxl

def normalize_string(input_str):
    nfkd_form = unicodedata.normalize('NFKD', input_str)
    return "".join([c for c in nfkd_form if not unicodedata.combining(c)]).replace('ñ', 'n')

def format_string(input_str):
    input_str = normalize_string(input_str)
    return input_str.lower().replace(' ', '-')

def build_url(marca, modelo, offset=None):
    base_url = f"https://autos.mercadolibre.com.ar/{marca}/{modelo}/"
    if offset:
        base_url += f"_Desde_{offset}"
    return base_url

def obtener_total_resultados(url, headers):
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        total_resultados_element = soup.find('span', class_='ui-search-search-result__quantity-results')
        total_resultados_text = total_resultados_element.text.strip()
        total_resultados = int(re.search(r'\d+', total_resultados_text.replace('.', '')).group())
        return total_resultados
    except Exception as e:
        print(f"Error al obtener el total de resultados: {e}")
        return 0

def obtener_precio_dolar():
    url = "https://api.exchangerate-api.com/v4/latest/USD"
    respuesta = requests.get(url)
    datos = respuesta.json()
    precio_dolar = datos["rates"]["ARS"]  # ARS es el código para la moneda argentina
    return precio_dolar

def seleccionar_marca_modelo():
    # URL de la página a scrappear
    url = "https://www.eleconomista.es/ecomotor/marcas/"

    # Encabezados para la solicitud HTTP
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36"
    }

    # Realizar la solicitud HTTP
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        print(f"Error al acceder a la página: {response.status_code}")
        exit()

    # Parsear el contenido HTML
    soup = BeautifulSoup(response.content, 'html.parser')

    # Encontrar las marcas de autos y sus modelos
    marcas = soup.find_all('h3', itemprop='name')

    # Crear un diccionario para almacenar las marcas y sus modelos
    autos = {}

    # Extraer los nombres de las marcas y sus modelos
    for marca in marcas:
        nombre_marca = marca.get_text(strip=True)
        modelos = marca.find_next('div', class_='li-versiones').find_all('li', itemprop='name')
        autos[nombre_marca] = [modelo.get_text(strip=True) for modelo in modelos]

    # Crear un menú para seleccionar la marca
    pregunta_marca = [
        inquirer.List('marca',
                      message="Selecciona una marca",
                      choices=list(autos.keys()))
    ]
    respuesta_marca = inquirer.prompt(pregunta_marca)
    marca_seleccionada = respuesta_marca['marca']

    # Crear un menú para seleccionar el modelo
    pregunta_modelo = [
        inquirer.List('modelo',
                      message=f"Selecciona un modelo de {marca_seleccionada}",
                      choices=autos[marca_seleccionada])
    ]
    respuesta_modelo = inquirer.prompt(pregunta_modelo)
    modelo_seleccionado = respuesta_modelo['modelo']

    return format_string(marca_seleccionada), format_string(modelo_seleccionado)

def obtener_datos_producto(soup):
    # Inicializar listas para almacenar los datos
    titulos = []
    precios = []
    monedas = []
    links = []
    imagenes = []
    anos = []
    kilometrajes = []
    ubicaciones = []

    # Buscar productos
    productos = soup.find_all('li', class_='ui-search-layout__item')

    for producto in productos:
        # Extraer título
        titulo = producto.find('a', class_='poly-component__title').get_text(strip=True)

        # Extraer precio
        precio = producto.find('span', class_='andes-money-amount__fraction').get_text(strip=True)
        moneda = producto.find('span', class_='andes-money-amount__currency-symbol').get_text(strip=True)

        #Agregar que si la moneda es $ multipleque el precio por 1200
        if moneda == '$':
            precio = precio.replace('$', '').replace('.', '').replace(',', '')
            precio_dolar = obtener_precio_dolar()
            precio = int(precio) / precio_dolar
            

            moneda = 'US$'
        else:
            precio = precio
            moneda = moneda

        # Extraer link
        link = producto.find('a', class_='poly-component__title')['href']

        # Extraer imagen
        imagen = producto.find('img')['src']

        # Extraer año y kilometraje
        atributos = producto.find_all('li', class_='poly-attributes-list__item')
        ano = 'N/A'
        kilometraje = 'N/A'
        for atributo in atributos:
            texto = atributo.get_text(strip=True)
            if re.search(r'\b(19|20)\d{2}\b', texto):
                ano = re.search(r'\b(19|20)\d{2}\b', texto).group(0)
            if 'Km' in texto:
                kilometraje = texto

        # Extraer ubicación
        ubicacion = producto.find('span', class_='poly-component__location').get_text(strip=True)

        # Agregar a las listas
        titulos.append(titulo)
        precios.append(precio)
        monedas.append(moneda)
        links.append(link)
        imagenes.append(imagen)
        anos.append(ano)
        kilometrajes.append(kilometraje)
        ubicaciones.append(ubicacion)

    return titulos, precios, monedas, links, imagenes, anos, kilometrajes, ubicaciones


def analyze_data(df):
    # Clean and convert data
    df['Precio'] = df['Precio'].str.replace('.', '').astype(float)
    df['Kilometraje'] = df['Kilometraje'].str.replace('Km', '').str.replace(' ', '').str.replace('.', '').astype(int)    
    # Group by year and calculate averages
    grouped = df.groupby('Ano').agg({
    'Precio': ['mean', 'min', 'max'],
    'Kilometraje': 'mean',
    'Link': ['min', 'max']
    }).reset_index()
    
    # Flatten multi-index columns
    grouped.columns = ['Ano', 'Precio_Promedio', 'Precio_Mas_Barato', 'Precio_Mas_Caro', 'Kilometraje_Promedio', 'Link_Mas_Barato', 'Link_Mas_Caro']    
    
    return grouped

def main():
    marca, modelo = seleccionar_marca_modelo()
    print(f"Marca seleccionada: {marca}")
    print(f"Modelo seleccionado: {modelo}")

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36"
    }

    # Construir la URL inicial para obtener el total de resultados
    url_inicial = build_url(marca, modelo)
    total_results = obtener_total_resultados(url_inicial, headers)
    print(f"Total de resultados encontrados: {total_results}")

    # Listas para almacenar los datos
    titulos = []
    precios = []
    monedas = []
    links = []
    imagenes = []
    anos = []
    kilometrajes = []
    ubicaciones = []

    offset = 0
    results_per_page = 48

    while offset < total_results:
        url = build_url(marca, modelo, offset if offset else None)
        print(f"Analizando URL: {url}")
        
        # Realizar la solicitud HTTP y analizar la página
        response = requests.get(url, headers=headers)
        soup = BeautifulSoup(response.content, 'html.parser')

        # Obtener los datos de cada producto
        datos_producto = obtener_datos_producto(soup)

        # Agregar los datos a las listas generales
        titulos.extend(datos_producto[0])
        precios.extend(datos_producto[1])
        monedas.extend(datos_producto[2])
        links.extend(datos_producto[3])
        imagenes.extend(datos_producto[4])
        anos.extend(datos_producto[5])
        kilometrajes.extend(datos_producto[6])
        ubicaciones.extend(datos_producto[7])

        offset += results_per_page

    # Crear un DataFrame con los datos extraídos
    df = pd.DataFrame({
        'Titulo': titulos,
        'Precio': precios,
        'Moneda': monedas,
        'Link': links,
        'Imagen': imagenes,
        'Ano': anos,
        'Kilometraje': kilometrajes,
        'Ubicación': ubicaciones
    })

    #obtener fecha de hoy para sumar al nombre de los archivos
    from datetime import date
    today = date.today()
    today = today.strftime("%d-%m-%Y")


    # Guardar el DataFrame en un archivo CSV
    df.to_excel(f'resultados_publicaciones_{marca}_{modelo}_{today}.xlsx', index=False)
    print(f"Datos guardados en 'resultados_publicaciones_{marca}_{modelo}_{today}.xlsx'")
    
    # Realizar análisis de precios
    analysis_df = analyze_data(df)
    analysis_df.to_excel(f'analisis_precios_{marca}_{modelo}_{today}.xlsx', index=False)
    print(f"Análisis de precios guardado en 'analisis_precios_{marca}_{modelo}_{today}.xlsx'")

if __name__ == '__main__':
    main()
