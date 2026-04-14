from fastapi import APIRouter, HTTPException, Query, status

from hercules_api.deps import SessionDep
from hercules_api.schemas.profile import CreateRecipeRequest, RecipeOut
from hercules_api.services.profile_service import (
    ProfileServiceError,
    create_recipe,
    recipe_per_serving_macros,
    search_recipes,
)

router = APIRouter(prefix="/recipes", tags=["recipes"])


def _to_recipe_out(recipe) -> RecipeOut:  # type: ignore[no-untyped-def]
    macros = recipe_per_serving_macros(recipe)
    return RecipeOut(
        id=recipe.id,
        name=recipe.name,
        servings=recipe.servings,
        notes=recipe.notes,
        created_at=recipe.created_at,
        ingredients=[
            {"id": i.id, "food_id": i.food_id, "servings": i.servings}
            for i in recipe.ingredients
        ],
        **macros,
    )


@router.post("", response_model=RecipeOut, status_code=201)
async def create_recipe_endpoint(
    payload: CreateRecipeRequest, session: SessionDep
) -> RecipeOut:
    try:
        recipe = await create_recipe(session, payload)
    except ProfileServiceError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    return _to_recipe_out(recipe)


@router.get("", response_model=list[RecipeOut])
async def search_recipes_endpoint(
    session: SessionDep,
    q: str = Query(default="", description="Name search (empty returns all)"),
    limit: int = Query(default=20, ge=1, le=50),
) -> list[RecipeOut]:
    recipes = await search_recipes(session, q, limit)
    return [_to_recipe_out(r) for r in recipes]
