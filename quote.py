# Quote Generator - Precision Concrete
def calculate_price(sqft, job_type, demo):
    if job_type == "driveway":
        price_per_sqft = 25
    elif job_type == "patio":
        price_per_sqft = 22
    else:
        price_per_sqft =28
        
    if demo == "yes":
        price_per_sqft += 7

    total = price_per_sqft * sqft
    return total

quote_number = "Q-061"   

# Get Client info
client_name = input("client name: ")
address = input("Address: ")
sqft = int(input("square footage: "))
job_type = input("job type (driveway/patio/foundation): ")
demo = input("Demo needed? (yes/no): ")

# Calculate
total = calculate_price(sqft, job_type, demo)
deposit = min(1000, total * 0.10)
# Print Quote Summary
print("\n---QUOTE SUMMARY ---")
print("Client:", client_name)
print("Address:", address)
print("Job type:", job_type)
print("Square footage:", sqft)
print("Demo included:", demo)
print("Total estimate: $", total)
print("quote number:", quote_number)
print("Deposit due: $", deposit)
print("---------------------")
# save quote to files
file_name = quote_number + ".text"

linesname = [
    "QUOTE SUMMARY",
    "Client: " + client_name,
    "Address: " + address,
    "Job type: " + job_type,
    "Square footage: " + str(sqft),
    "Demo included: " + demo,
    "Total estimate: $" + str(total),
    "Quote number: " + quote_number,
    "Deposit due: $" + str(deposit)
]

with open(file_name, "w") as f:
    for line in lines:
        f.write(line + "\n")

print("Quote saved as", file_name)    