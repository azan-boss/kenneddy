from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Favourite
from .serializers import FavouriteMergeSerializer, FavouriteSerializer


class FavouriteListCreateView(APIView):
    """
    GET  /api/favourites/?kind=wishlist  — authenticated user's own favourites.
    POST /api/favourites/                — add a favourite.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = Favourite.objects.filter(user=request.user)
        kind = request.query_params.get("kind")
        if kind:
            qs = qs.filter(kind=kind)
        serializer = FavouriteSerializer(qs, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = FavouriteSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(user=request.user)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class FavouriteDeleteView(APIView):
    """
    DELETE /api/favourites/{id}/

    Returns 404 whether the favourite doesn't exist OR belongs to another user
    — don't leak existence of other users' data.
    """

    permission_classes = [IsAuthenticated]

    def delete(self, request, pk):
        try:
            fav = Favourite.objects.get(pk=pk, user=request.user)
        except Favourite.DoesNotExist:
            return Response({"detail": "Favourite nahi mila."}, status=status.HTTP_404_NOT_FOUND)

        fav.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class FavouriteMergeView(APIView):
    """
    POST /api/favourites/merge/

    Accepts {"items": [{dish_slug, dish_name, dish_image, price, kind}, ...]}
    and bulk get_or_creates rows for the authenticated user.
    Duplicates are silently ignored — no error, no duplicate rows.
    Returns counts of created vs already-existing.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = FavouriteMergeSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        items   = serializer.validated_data["items"]
        created = 0
        existed = 0

        for item in items:
            _, was_created = Favourite.objects.get_or_create(
                user      = request.user,
                dish_slug = item["dish_slug"],
                kind      = item["kind"],
                defaults  = {
                    "dish_name":  item["dish_name"],
                    "dish_image": item.get("dish_image", ""),
                    "price":      item["price"],
                },
            )
            if was_created:
                created += 1
            else:
                existed += 1

        return Response(
            {
                "detail":  f"{created} created, {existed} already existed.",
                "created": created,
                "existed": existed,
            },
            status=status.HTTP_200_OK,
        )
