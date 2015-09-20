class nameddict(dict):
    """ Provides dictionary whose keys are accessible via the property
    syntax: `obj.key`
    """
    def __init__(self, *args, **kwargs):
        super(nameddict, self).__init__(*args, **kwargs)
        self.__dict__ = self
        self.__namify(self.__dict__)

    def __namify(self, a_dict):
        for key in a_dict.keys():
            if type(a_dict[key]) == dict:
                a_dict[key] = nameddict(a_dict[key])

    def __setitem__(self, key, value):
        if type(value) == dict:
            value = nameddict(value)
        super(nameddict, self).__setitem__(key, value)

    def __setattr__(self, key, value):
        if key != '__dict__' and type(value) == dict:
            value = nameddict(value)
        super(nameddict, self).__setattr__(key, value)
