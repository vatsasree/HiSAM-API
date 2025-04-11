from src.ml_models.LineTR.infer_new import Infer
import time


model = Infer()
start = time.time()
model.process_image('040005.jpg')
print((time.time() - start))