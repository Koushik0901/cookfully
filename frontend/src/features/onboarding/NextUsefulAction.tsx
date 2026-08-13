import { ArrowRight, BookOpenText, CalendarDays, ShoppingBasket } from "lucide-react";
import { Link } from "react-router-dom";

import { Button } from "../../components";

type NextAction = "recipe" | "plan" | "grocery";

const content: Record<NextAction, { title: string; body: string; label: string; to: string; Icon: typeof BookOpenText }> = {
  recipe: { title: "Start with one recipe", body: "A familiar meal is enough. You can keep it simple and add the details later.", label: "Create a recipe", to: "/app/recipes/new", Icon: BookOpenText },
  plan: { title: "Give the week one anchor", body: "Add a recipe to one meal slot; the rest can stay flexible.", label: "Open this week", to: "/app/plan", Icon: CalendarDays },
  grocery: { title: "Build the list from your plan", body: "Once a few meals are chosen, Cookfully gathers what you need in one calm shopping pass.", label: "See the meal plan", to: "/app/plan", Icon: ShoppingBasket },
};

export function NextUsefulAction({ action }: { action: NextAction }) {
  const value = content[action];
  const Icon = value.Icon;
  return <aside className="next-useful-action"><Icon aria-hidden="true" /><div><strong>{value.title}</strong><p>{value.body}</p></div><Button asChild className="button--secondary"><Link to={value.to}>{value.label}<ArrowRight aria-hidden="true" /></Link></Button></aside>;
}
