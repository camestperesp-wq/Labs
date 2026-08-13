# importar.py

import pandas as pd
import sqlite3
from collections import defaultdict

ARCHIVO_EXCEL = "horario_filtrado.xlsx"

# ============================================================
#  MAPEOS
# ============================================================

DIAS_MAP = {
    "LUNES": "Lunes",
    "MARTES": "Martes",
    "MIERCOLES": "Miercoles",
    "JUEVES": "Jueves",
    "VIERNES": "Viernes",
    "SABADO": "Sabado",
    "DOMINGO": "Domingo"
}

MAPEO_LABS = {
    # Solo los laboratorios de física (para este script)
    "LABORATORIO 1 CAP(31)": "FLU 101",
    "LABORATORIO 2 CAP(31)": "PRO 102",
    "LABORATORIO 3 CAP(31)": "MEC 103",
    "LABORATORIO FISICA 1 CAP(24)": "NEW 408",
    "LABORATORIO DE FISICA 02 CAP(18)": "ELE 509",
    "LABORATORIO DE FISICA 03 CAP(18)": "OND 510"
}

HORAS_MAP = {
    "6AM-7AM": "06:00-07:00", "7AM-8AM": "07:00-08:00",
    "8AM-9AM": "08:00-09:00", "9AM-10AM": "09:00-10:00",
    "10AM-11AM": "10:00-11:00", "11AM-12M": "11:00-12:00",
    "12M-1PM": "12:00-13:00", "1PM-2PM": "13:00-14:00",
    "2PM-3PM": "14:00-15:00", "3PM-4PM": "15:00-16:00",
    "4PM-5PM": "16:00-17:00", "5PM-6PM": "17:00-18:00",
    "6PM-7PM": "18:00-19:00", "7PM-8PM": "19:00-20:00",
    "8PM-9PM": "20:00-21:00", "9PM-10PM": "21:00-22:00"
}

MAPEO_CARRERAS = {
    "INGENIERIA ELECTRONICA": "Ing. Electrónica",
    "INGENIERIA ELECTRICA": "Ing. Eléctrica",
    "INGENIERIA DE SISTEMAS": "Ing. De Sistema",
    "INGENIERIA INDUSTRIAL": "Ing. Industrial",
    "INGENIERIA CATASTRAL": "Ing. Catastral",
    "POSGRADOS": "Posgrados"
}

# ============================================================
#  FUNCIONES
# ============================================================

def normalizar_dia(dia):
    return DIAS_MAP.get(dia.strip().upper(), dia)

def mapear_laboratorio(salon):
    salon_limpio = salon.strip()
    for clave, valor in MAPEO_LABS.items():
        if clave.replace(" ", "") in salon_limpio.replace(" ", "") or salon_limpio.replace(" ", "") in clave.replace(" ", ""):
            return valor
    return None

def formatear_asignatura(asignatura, grupo):
    partes = asignatura.split(' - ', 1)
    nombre = partes[1].strip() if len(partes) > 1 else asignatura.strip()
    if grupo and str(grupo).strip():
        return f"{nombre} {grupo}"
    return nombre

def extraer_y_mapear_carrera(proyecto):
    if not proyecto:
        return ""
    
    partes = proyecto.split(' - ', 1)
    if len(partes) > 1:
        nombre_carrera = partes[1].strip().upper()
    else:
        nombre_carrera = proyecto.strip().upper()
    
    for clave, valor in MAPEO_CARRERAS.items():
        if clave in nombre_carrera or nombre_carrera in clave:
            return valor
    
    return nombre_carrera.capitalize()

def convertir_hora(hora_str):
    return HORAS_MAP.get(hora_str.strip().upper(), hora_str)

def obtener_numero_hora(hora_str):
    try:
        return int(hora_str.split('-')[0].split(':')[0])
    except:
        return 0

def agrupar_por_pares(df):
    registros = []
    
    for _, row in df.iterrows():
        lab = mapear_laboratorio(row['Salón'])
        if not lab:
            continue
        
        hora = convertir_hora(row['Hora'])
        if not hora:
            continue
        
        carrera = ""
        if 'Proyecto' in df.columns:
            carrera = extraer_y_mapear_carrera(row.get('Proyecto', ''))
        
        registros.append({
            'dia': normalizar_dia(row['Día']),
            'hora': hora,
            'laboratorio': lab,
            'asignatura': formatear_asignatura(row['Asignatura'], row['Grupo']),
            'profesor': row['Docente'] if pd.notna(row['Docente']) else "",
            'carrera': carrera
        })
    
    grupos = defaultdict(list)
    for reg in registros:
        clave = (reg['dia'], reg['laboratorio'], reg['asignatura'], reg['profesor'], reg['carrera'])
        grupos[clave].append(reg)
    
    resultado = []
    for clave, items in grupos.items():
        dia, lab, asignatura, profesor, carrera = clave
        items.sort(key=lambda x: obtener_numero_hora(x['hora']))
        
        i = 0
        while i < len(items):
            hora_actual = items[i]['hora']
            num_actual = obtener_numero_hora(hora_actual)
            
            encontrado_par = False
            for j in range(i + 1, len(items)):
                hora_siguiente = items[j]['hora']
                num_siguiente = obtener_numero_hora(hora_siguiente)
                
                if num_siguiente == num_actual + 1:
                    hora_bloque = f"{num_actual:02d}:00-{num_siguiente + 1:02d}:00"
                    resultado.append({
                        'dia': dia,
                        'hora': hora_bloque,
                        'laboratorio': lab,
                        'asignatura': asignatura,
                        'profesor': profesor,
                        'carrera': carrera
                    })
                    i = j + 1
                    encontrado_par = True
                    break
            
            if not encontrado_par:
                hora_sistema = f"{num_actual:02d}:00-{num_actual + 2:02d}:00"
                resultado.append({
                    'dia': dia,
                    'hora': hora_sistema,
                    'laboratorio': lab,
                    'asignatura': asignatura,
                    'profesor': profesor,
                    'carrera': carrera
                })
                i += 1
    
    return resultado

# ============================================================
#  FUNCIÓN PRINCIPAL
# ============================================================

def reimportar_fisica():
    print("=" * 60)
    print("🧹 REIMPORTANDO LABORATORIOS DE FÍSICA")
    print("=" * 60)

    # 1. Leer Excel
    try:
        df = pd.read_excel(ARCHIVO_EXCEL)
    except Exception as e:
        print(f"❌ Error al leer: {e}")
        return

    print(f"✅ {len(df)} registros leídos")

    # 2. Mostrar laboratorios de física en el Excel
    labs_fisica_excel = []
    for lab in df['Salón'].unique():
        if mapear_laboratorio(lab):
            labs_fisica_excel.append(lab)
    
    print("\n📋 Laboratorios de física encontrados en el Excel:")
    for lab in labs_fisica_excel:
        print(f"   - {lab} → {mapear_laboratorio(lab)}")

    # 3. Conectar a la BD
    with sqlite3.connect('mi_agenda.db') as conn:
        c = conn.cursor()
        
        # 4. ELIMINAR SOLO LOS REGISTROS DE LABORATORIOS DE FÍSICA
        labs_fisica_sistema = ["FLU 101", "PRO 102", "MEC 103", "NEW 408", "ELE 509", "OND 510"]
        
        eliminados = 0
        for lab in labs_fisica_sistema:
            c.execute("DELETE FROM horario_fijo WHERE laboratorio = ?", (lab,))
            eliminados += c.rowcount
        
        print(f"\n🗑️ Eliminados {eliminados} registros de laboratorios de física")

        # 5. Procesar y agrupar datos del Excel
        print("\n🔄 Procesando datos del Excel...")
        registros = agrupar_por_pares(df)
        print(f"   ✅ {len(registros)} bloques generados")

        # 6. Insertar solo los que son de física
        insertados = 0
        errores = 0
        
        labs_validos_fisica = labs_fisica_sistema
        
        print("\n📥 Insertando registros de física...")
        for reg in registros:
            try:
                if reg['laboratorio'] not in labs_validos_fisica:
                    continue  # Saltar los que no son de física
                
                c.execute("""
                    INSERT INTO horario_fijo 
                    (dia_semana, hora, laboratorio, asignatura, carrera, monitor, profesor)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (reg['dia'], reg['hora'], reg['laboratorio'], 
                      reg['asignatura'], reg['carrera'], "", reg['profesor']))
                insertados += 1
                
                if insertados % 10 == 0:
                    print(f"   ... {insertados} insertados")
                
            except Exception as e:
                print(f"   ❌ Error: {e}")
                errores += 1
        
        conn.commit()
    
    print("\n" + "=" * 60)
    print("📊 RESUMEN")
    print("=" * 60)
    print(f"🗑️ Eliminados: {eliminados}")
    print(f"✅ Insertados: {insertados}")
    print(f"⚠️ Errores: {errores}")
    print("\n🎉 ¡Listo!")

if __name__ == "__main__":
    reimportar_fisica()