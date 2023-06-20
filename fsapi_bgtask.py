from flask_restful import Resource
from fsapi_utils import *
from celery.result import AsyncResult


class BackgroundTask(Resource):
    @require_token
    @os_exception_handle
    def get(self, id: str):
        result = AsyncResult(id)
        print(result)
        return {
            "status": result.status,
            "info": result.info,
        }
    
        
