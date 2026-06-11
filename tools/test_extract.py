import importlib.util
from pathlib import Path
import sys

nlp_path = Path(__file__).parents[1] / 'app' / 'services' / 'nlp.py'
spec = importlib.util.spec_from_file_location('nlp_mod', str(nlp_path))
nlp_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(nlp_mod)

skills = ['Python','Machine Learning','Deep Learning','TensorFlow','OpenCV','YOLO','OCR','Computer Vision','Data Science','Scikit-learn','Git','GitHub','FastAPI','MongoDB','React.js']
text = '''Programming Languages: Python, JavaScript (ES6+), SQL
Frontend Development: React.js, HTML5, CSS3, Responsive Design, Component Architecture
Backend Development: Node.js, Express.js, REST API Design, JWT Authentication, Bcrypt
Database Technologies: MongoDB, Mongoose ODM, MySQL
AI / Machine Learning: Machine Learning, Deep Learning, CNNs, TensorFlow, YOLOv8, Scikit-learn
Computer Vision & OCR: OpenCV, EasyOCR, Image Processing, Real-Time Object Detection
Data Science: Data Analysis, Feature Engineering, Model Evaluation, Data Preprocessing
Tools & Platforms: Git, GitHub, Jupyter Notebook, VS Code, FastAPI
'''

print('\n=== Running extract_skills_from_text test ===')
result = nlp_mod.extract_skills_from_text(text, skills)
print('Extracted skills:', result)
