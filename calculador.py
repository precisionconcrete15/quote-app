def calcular_trabajo(sqft, demo):
  if demo == "si":
    precio_por_sqft = 32  
  else:
    precio_por_sqft = 25
  total = precio_por_sqft * sqft
  return total

sqft = int(input("Cuantos sqft? "))
demo = input("Incluye demolicion? (si/no) ")
resultado = calcular_trabajo(sqft, demo)
print("El trabajo cuesta $", resultado)
