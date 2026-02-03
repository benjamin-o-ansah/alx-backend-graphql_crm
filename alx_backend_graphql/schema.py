import graphene
from crm.schema import CRMQuery


class Query(CRMQuery, graphene.ObjectType):
    """
    Root GraphQL query composed from app-level queries
    """
    pass


schema = graphene.Schema(query=Query)

