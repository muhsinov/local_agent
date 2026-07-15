from app.api.errors import ApiError


class ApprovalError(ApiError):
    pass


class ApprovalFinalizationError(ApprovalError):
    pass
