import sys
import os

# Añade la raíz del proyecto al path de Python
# para que pytest pueda encontrar el módulo src
sys.path.insert(0, os.path.dirname(__file__))
