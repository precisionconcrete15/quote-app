def	calculate_work(sqft,	demo):
	if	demo	==	"yes":
		price_per_sqft	=	32
	else:
		price_per_sqft	=	25
	total	=	price_per_sqft	*	sqft
	return	total

sqft	=	int(input("How	many	sqft?	"))
demo	=	input("Includes	demolition?	(yes/no)	")
result	=	calculate_work(sqft,	demo)
print("The	work	cost	$",	result)
