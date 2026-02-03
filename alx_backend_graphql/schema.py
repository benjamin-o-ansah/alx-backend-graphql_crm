import graphene
from crm.schema import CRMQuery,CRMMutation


class Query(CRMQuery, graphene.ObjectType):
    """
    Root GraphQL query composed from app-level queries
    """
    pass

class Mutation(CRMMutation, graphene.ObjectType):
    pass


schema = graphene.Schema(query=Query, mutation=Mutation)

