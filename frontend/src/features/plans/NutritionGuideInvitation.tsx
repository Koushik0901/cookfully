import { HeartPulse } from "lucide-react";
import { Link } from "react-router-dom";

import { Button } from "../../components";
import { RecipeFallbackArt } from "../../components/cookfully/RecipeFallbackArt";

export function NutritionGuideInvitation({ compact = false }: { compact?: boolean }) {
  return (
    <section className={`nutrition-invitation${compact ? " nutrition-invitation--compact" : ""}`} aria-label="Add nutrition guidance">
      {!compact ? <RecipeFallbackArt title="fresh produce" /> : null}
      <div>
        <p className="eyebrow">Nutrition guidance</p>
        <h2>Plan the food now. Add your guide when you’re ready.</h2>
        <p>Your meals do not need numbers to belong here. A personal guide lets Cookfully help balance energy, protein, carbohydrate, and fat while you plan.</p>
        <Button asChild><Link to="/app/goals"><HeartPulse aria-hidden="true" />Add nutrition guidance</Link></Button>
      </div>
    </section>
  );
}
