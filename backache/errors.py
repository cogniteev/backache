class BackacheError(Exception):
    def __init__(self, operation, uri, message):
        super(BackacheError, self).__init__(message.format(
            operation=operation,
            uri=uri
        ))
        self.operation = operation
        self.uri = uri


class UnknownResource(BackacheError):
    def __init__(self, operation, uri):
        super(UnknownResource, self).__init__(
            operation,
            uri,
            u"Unknown resource: {operation}/{uri}"
        )


class ResourceAlreadyExists(BackacheError):
    def __init__(self, operation, uri):
        super(ResourceAlreadyExists, self).__init__(
            operation,
            uri,
            u"Resource already exists: {operation}/{uri}"
        )


class ResourceLocked(BackacheError):
    def __init__(self, operation, uri):
        super(ResourceLocked, self).__init__(
            operation,
            uri,
            u"Resource is locked: {operation}/{uri}"
        )


class ResourceNotLocked(BackacheError):
    def __init__(self, operation, uri):
        super(ResourceNotLocked, self).__init__(
            operation,
            uri,
            u"Resource is not locked: {operation}/{uri}"
        )
