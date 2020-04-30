def getfeature_fromeedict(eecollection, attribute, featname):
    '''get image collection properties'''
    aux = []
    for feature in range(len(eecollection['features'])):

        ## get data from the dictionary
        datadict = eecollection['features'][feature][attribute][featname]
        ## check if it has info
        aux.append(datadict)
    return (aux)



