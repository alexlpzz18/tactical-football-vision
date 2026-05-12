import cv2
import os
import argparse


def extract_frames(video_path, output_dir, fps=1):
    """
    Extrae frames de un vídeo a una frecuencia determinada.

    Args:
        video_path: Ruta al archivo de vídeo
        output_dir: Carpeta donde guardar los frames
        fps: Cuántos frames extraer por segundo de vídeo (default: 1)
    """
    # Abre el vídeo
    cap = cv2.VideoCapture(video_path)

    if not cap.isOpened():
        print(f"Error: no se puede abrir el vídeo {video_path}")
        return

    # Obtiene información del vídeo
    video_fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total_frames / video_fps

    print(f"Vídeo: {os.path.basename(video_path)}")
    print(f"FPS originales: {video_fps:.1f}")
    print(f"Total frames: {total_frames}")
    print(f"Duración: {duration:.1f} segundos")

    # Calcula cada cuántos frames extraer uno
    frame_interval = int(video_fps / fps)

    # Crea la carpeta de salida si no existe
    os.makedirs(output_dir, exist_ok=True)

    frame_count = 0
    saved_count = 0

    while True:
        ret, frame = cap.read()

        # ret es False cuando el vídeo termina
        if not ret:
            break

        # Guarda el frame si toca según el intervalo
        if frame_count % frame_interval == 0:
            frame_name = f"frame_{saved_count:05d}.jpg"
            frame_path = os.path.join(output_dir, frame_name)
            cv2.imwrite(frame_path, frame)
            saved_count += 1

        frame_count += 1

    cap.release()
    print(f"Frames guardados: {saved_count}")
    print(f"Guardados en: {output_dir}\n")


def main():
    parser = argparse.ArgumentParser(
        description="Extrae frames de vídeos de fútbol"
    )
    parser.add_argument(
        "--videos_dir",
        required=True,
        help="Carpeta con los vídeos de entrada"
    )
    parser.add_argument(
        "--output_dir",
        required=True,
        help="Carpeta donde guardar los frames"
    )
    parser.add_argument(
        "--fps",
        type=int,
        default=1,
        help="Frames por segundo a extraer (default: 1)"
    )
    args = parser.parse_args()

    # Procesa todos los vídeos de la carpeta
    video_extensions = (".mp4", ".avi", ".mov", ".mkv")
    videos = [
        f for f in os.listdir(args.videos_dir)
        if f.endswith(video_extensions)
    ]

    if not videos:
        print("No se encontraron vídeos en la carpeta especificada")
        return

    print(f"Vídeos encontrados: {len(videos)}\n")

    for video in videos:
        video_path = os.path.join(args.videos_dir, video)
        video_name = os.path.splitext(video)[0]
        video_output_dir = os.path.join(args.output_dir, video_name)
        extract_frames(video_path, video_output_dir, args.fps)


if __name__ == "__main__":
    main()