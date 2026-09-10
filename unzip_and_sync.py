import os
import zipfile
import shutil

# Rutas del proyecto
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INBOX_DIR = os.path.join(BASE_DIR, "data", "radar", "inbox_zips")
RAW_DIR = os.path.join(BASE_DIR, "data", "radar", "raw")

os.makedirs(INBOX_DIR, exist_ok=True)
os.makedirs(RAW_DIR, exist_ok=True)

zip_files = [f for f in os.listdir(INBOX_DIR) if f.lower().endswith(".zip")]

print("=" * 60)
print("  YIELDPADEL - INGESTA DIARIA DE CHATS DE WHATSAPP (.ZIP)")
print("=" * 60)

if not zip_files:
    print(f"\n[!] No hay archivos .zip en la carpeta:")
    print(f"    {INBOX_DIR}")
    print("\nGuarda o arrastra ahí tus archivos descargados de WhatsApp")
    print("Ejemplo: data/radar/inbox_zips/lapala_sept.zip\n")
    input("Presiona Enter para salir...")
    exit()

print(f"\n[*] Encontrados {len(zip_files)} archivo(s) .zip para procesar.\n")

for zip_name in zip_files:
    zip_path = os.path.join(INBOX_DIR, zip_name)
    club_name = os.path.splitext(zip_name)[0]
    dest_txt = os.path.join(RAW_DIR, f"{club_name}.txt")

    print(f"--> Procesando: {zip_name} ...")
    try:
        with zipfile.ZipFile(zip_path, 'r') as z:
            # Buscar el archivo .txt dentro del zip (_chat.txt o similar)
            txt_candidates = [m for m in z.namelist() if m.lower().endswith(".txt")]
            if txt_candidates:
                target_in_zip = txt_candidates[0]
                with z.open(target_in_zip) as source, open(dest_txt, "wb") as target:
                    shutil.copyfileobj(source, target)
                print(f"    [V] Descomprimido y renombrado como: {club_name}.txt")
            else:
                print(f"    [!] No se encontro ningún .txt dentro de {zip_name}")
    except Exception as e:
        print(f"    [X] Error extrayendo {zip_name}: {e}")

print("\n" + "=" * 60)
print(f"  TODOS LOS .TXT QUEDARON LISTOS EN: {RAW_DIR}")
print("=" * 60 + "\n")

resp = input("¿Deseas procesar estos chats y subirlos a Supabase ahora mismo? (S/N): ").strip().upper()

if resp == "S":
    print("\n[*] 1. Extrayendo y deduplicando convocatorias...")
    try:
        import app.services.radar_service as rs
        res = rs.process_batch_raw_folder()
        print(f"    Resultado: {res}")
    except Exception as e:
        print(f"    [!] Error en radar_service: {e}")

    print("\n[*] 2. Subiendo registros a Supabase...")
    os.system("python upload_radar_to_supabase.py")

    print("\n[*] 3. Actualizando perfiles en CRM...")
    os.system("python build_crm_profiles.py")

    print("\n[V] Pipeline completado con éxito.")
else:
    print("\n[i] Archivos .txt listos en raw. Puedes correr el pipeline cuando quieras.")

input("\nPresiona Enter para finalizar...")