# The Nexus Story JSON Schema Reference

This document provides the complete technical specification for the JSON story format used by **The Nexus (النكسس)** bot.

---

## 1. File Naming Convention

Every story file must be named according to this format:
`{world_type}_{descriptive_slug}.json`

**Examples:**
- `solo_room_404.json`
- `fantasy_cursed_heir.json`
- `future_rented_memory.json`

---

## 2. Top-Level Fields

The root of the story JSON file is an object containing the following top-level fields:

| Field Name | Type | Required / Optional | Description | Valid Values / Format | Default |
|:---|:---|:---|:---|:---|:---|
| `id` | String | **Required** | Unique story identifier. Must match the filename slug. | e.g. `"solo_room_404"` | None |
| `title` | String | **Required** | Arabic title of the story shown to players. | e.g. `"مفتاح الغرفة 404"` | None |
| `summary` | String | **Required** | Arabic story summary/description shown in selection menus. | e.g. `"تعود إلى فندق الياسمين المهجور..."` | None |
| `world` | String | **Required** | Arabic name of the world. Must match the `world_type`. | See World & Theme Catalog below | None |
| `world_type`| String | **Required** | English identifier of the world. | `solo`, `fantasy`, `past`, `future`, `alternate`, `multi` | None |
| `theme` | String | **Required** | Arabic category/theme name matching the catalog. | See World & Theme Catalog below | None |
| `game_mode` | String | **Required** | Gameplay mode. Single player vs multiplayer. | `"single"` or `"multi"` | None |
| `start_scene`| String | **Required** | Node key where the story begins. | Typically `"start"` | None |
| `spine` | Object | **Required** | The narrative backbone structure (6 fields). | See Spine Object below | None |
| `flags` | Array | Optional | List of unique flags used in the story. | Array of Flag Objects | `[]` |
| `perspectives`| Array | Optional | Multiple POVs for alternate starts or playthroughs. | Array of Perspective Objects | `[]` |
| `nodes` | Object | **Required** | Dictionary of all story nodes. | Key: node ID; Value: Node Object | None |

---

## 3. Spine Object

The `spine` object defines the narrative backbone of the story. It must contain exactly these 6 fields in Arabic:

*   **`wound`** (String): The protagonist's defining mistake or trauma before the story starts.
*   **`lie`** (String): The false belief the protagonist holds that is challenged during the story.
*   **`trigger`** (String): The inciting incident that forces action now.
*   **`complication`** (String): The point where the simple solution fails due to the protagonist's wound.
*   **`revelation`** (String): The twist or core truth that reframes earlier events.
*   **`verdict`** (String): The ultimate moral or physical consequence of the player's choices.

---

## 4. Flags Array

An optional list of flags used to track player choices. Each object in the array contains:
*   **`name`** (String): Unique identifier of the flag (e.g. `"read_notes"`).
*   **`description`** (String): Brief explanation of what setting this flag represents.

---

## 5. Perspectives Array

For stories that support multiple perspectives (POVs). Each object contains:
*   **`id`** (String): Unique identifier for the POV.
*   **`label`** (String): Arabic name of the character (e.g. `"المحقق"`).
*   **`emoji`** (String): Discord emoji representing the character.
*   **`description`** (String): Arabic description of the perspective.
*   **`start_node`** (String): Key of the node this perspective starts at.

---

## 6. Nodes Object

The `nodes` object contains the actual gameplay steps. Each node has a unique string key (format: `node_[descriptive_name]`) and has the following structure:

*   **`type`** (String, **Required**): The category of the node. Valid values:
    *   `opening`: The story's introduction.
    *   `discovery`: Revealing new clues or information.
    *   `decision`: A branch where the player chooses a path.
    *   `consequence`: A scene resolving previous actions/flags.
    *   `escalation`: Raising tension or stakes.
    *   `revelation`: A major plot twist node.
    *   `breath`: A slower-paced, atmospheric reflection node.
    *   `climax`: The final confrontation of the story.
    *   `ending`: Terminal nodes containing the story outcome.
*   **`text`** (String, **Required**): The narrative content of the node written in clear, simple Arabic (6-8 sentences maximum, present tense, second person "أنت").
*   **`is_ending`** (Boolean, Optional): Must be set to `true` on ending nodes. Defaults to `false`.
*   **`image_url`** (String, Optional): Link to an image displayed with the node.
*   **`choices`** (Array, **Required** unless `is_ending` is `true`): List of Choice Objects (maximum 4). Ending nodes must have an empty choices array or omit it.

---

## 7. Choice Object

Each choice inside the `choices` array of a node represents an action the player can take:

*   **`label`** (String, **Required**): Short, active Arabic description of the choice (under 40 characters). Must be an action, never a question.
*   **`next`** (String, **Required**): The key of the node this choice leads to.
*   **`sets_flag`** (String, Optional): Flag name to set to `true` when this choice is selected.
*   **`requires_flag`** (String, Optional): Flag name required to display/choose this option.
*   **`color`** (String, Optional): Button style. Valid values: `"primary"`, `"secondary"`, `"success"`, `"danger"`. Defaults to `"primary"`.
*   **`points_reward`** (Integer, Optional): Points awarded to the player. Defaults to `0`.
*   **`required_points`** (Integer, Optional): Points required to choose this action.
*   **`reputation`** (String, Optional): Reputation adjustments associated with this choice.

---

## 8. World & Theme Catalog

Valid combinations of `world`, `world_type`, and `theme` (Arabic category name) defined in the catalog:

### Solo Worlds (`game_mode: "single"`)

| `world_type` | `world` | Valid `theme` Categories |
|:---|:---|:---|
| **`solo`** | `"القصص الفردية"` | `"التحقيق الجنائي"`, `"الرعب النفسي"`, `"النجاة والكوارث"`, `"الاختراق والسرقات التقنية"`, `"التشويق السياسي"`, `"الفانتازيا المظلمة"`, `"الغموض العلمي"`, `"الهروب من الأسر"`, `"جرائم وتحقيقات"`, `"رعب نفسي"`, `"ظلام اجتماعي"`, `"بقاء وانهيار"`, `"أسرار مدفونة"` |
| **`fantasy`**| `"الفانتازيا"` | `"عروش مشققة"`, `"حروب لا تنتهي"`, `"أحلام الفرسان"`, `"ساحرات وأسرار"`, `"الظلام يحكم"` |
| **`past`** | `"الماضي"` | `"حضارات على الحافة"`, `"الحاكم والشعب"`, `"جواسيس التاريخ"`, `"ثورات وانتفاضات"`, `"السفر عبر التاريخ"` |
| **`future`** | `"المستقبل"` | `"ذكاء اصطناعي يتمرد"`, `"كوكب محتضر"`, `"مستعمرات الفضاء"`, `"هوية في عالم مزيف"`, `"الحرب الأخيرة"` |
| **`alternate`**| `"الواقع البديل"`| `"لو التاريخ تغير"`, `"نسخة أخرى منك"`, `"قوانين مختلفة"`, `"الغزو الصامت"`, `"الواقع يتكسر"` |

### Multiplayer Worlds (`game_mode: "multi"`)

| `world_type` | `world` | Valid `theme` Categories |
|:---|:---|:---|
| **`multi`** | `"قصص جماعية"` | `"نجاة الفريق"`, `"المعضلات الأخلاقية"`, `"سياسة الممالك"`, `"أزمات الفضاء"`, `"تفشي العدوى"`, `"بعثات الأطلال"`, `"التمرد والصراعات"`, `"اختبارات أسطورية"` |

---

## 9. Minimal Valid Story Example

Below is a minimal, structurally complete story in JSON format:

```json
{
  "id": "solo_minimal_demo",
  "title": "العثور على البوابة",
  "summary": "تتبع مذكرات مفقودة في محاولة لتجنب لعنة القلعة القديمة قبل فوات الأوان.",
  "world": "القصص الفردية",
  "world_type": "solo",
  "theme": "أسرار مدفونة",
  "game_mode": "single",
  "start_scene": "start",
  "spine": {
    "wound": "يوسف تخلى عن صديقه في سرداب القلعة لينقذ نفسه.",
    "lie": "يعتقد يوسف أن صديقه مات مباشرة وأنه لم يكن بوسعه مساعدته.",
    "trigger": "رسالة غامضة من القلعة تحمل خط صديقه المفقود.",
    "complication": "تنشيط الفخاخ المغناطيسية للقلعة وانقطاع الاتصال بالعالم الخارجي.",
    "revelation": "الصديق ما زال حياً ويتحكم بالفخاخ للانتقام من يوسف.",
    "verdict": "مواجهة الصديق ودفع ثمن الهرب القديم بالتضحية أو الهلاك."
  },
  "flags": [
    {
      "name": "found_diary",
      "description": "عثرت على مذكرات البناء القديمة"
    }
  ],
  "nodes": {
    "start": {
      "type": "opening",
      "text": "رائحة الحبر القديم تملأ الغرفة، والضوء الشاحب يمر عبر النافذة المغبرة. كل شيء هادئ هنا في مكتبة القلعة، باستثناء صوت دقات الساعة المعلقة التي لم تعمل منذ عقود. أمامك خريطة قديمة ممزقة ومفكرة صغيرة ذات قفل حديدي مهشم. الخيار أمامك إما أن تتفحص الخريطة لمعرفة الطريق، أو تقرأ المفكرة المتربة.",
      "choices": [
        {
          "label": "تقرأ المفكرة القديمة",
          "next": "node_read_diary",
          "sets_flag": "found_diary"
        },
        {
          "label": "تتفحص الخريطة الممزقة",
          "next": "node_map_route"
        }
      ]
    },
    "node_read_diary": {
      "type": "discovery",
      "text": "تفتح المفكرة لتجد كتابات صديقك المفقود يشتكي فيها من رطوبة الممرات وخوفه من خيانتك. في الصفحة الأخيرة كتب أن مفتاح المخرج يقع خلف لوحة الفارس في البهو الرئيسي للقلعة. تشعر بذنب شديد يجمد أطرافك وأنت تتذكر تلك الليلة المشؤومة. الآن الخيار أمامك إما الذهاب للبهو مباشرة، أو التحقق من القبو المظلم المجاورة.",
      "choices": [
        {
          "label": "تذهب إلى البهو مباشرة",
          "next": "node_hall"
        },
        {
          "label": "تتحقق من القبو المظلم",
          "next": "node_basement"
        }
      ]
    },
    "node_map_route": {
      "type": "decision",
      "text": "تتفحص الخريطة وتلاحظ مساراً سرياً مmarked باللون الأحمر يمر عبر سرداب القلعة الضيق. تشعر بنسمات باردة تهب من الفتحة الأرضية بجانبك، وصوت همس غير واضح يأتي من الأسفل. الخيار أمامك إما النزول للسرداب الضيق مباشرة، أو التوجه صوب قاعة العرش الكبرى بحثاً عن مخرج آخر.",
      "choices": [
        {
          "label": "تنزل عبر السرداب الأرضي",
          "next": "node_basement"
        },
        {
          "label": "تتجه لقاعة العرش",
          "next": "node_hall"
        }
      ]
    },
    "node_basement": {
      "type": "escalation",
      "text": "تنزل السلم الحجري الرطب وتشعر ببرودة صقيعية تمنعك من التنفس بشكل مريح. فجأة تنغلق الفتحة العلوية خلفك وتجد نفسك محاصراً في الظلام، بينما يتردد صدى ضحكة مألوفة لصديقك المفقود. تدرك أنه فخ أعد بعناية للامساك بك. لا تملك خيارات سوى المحاولة والمغامرة.",
      "choices": [
        {
          "label": "تحاول كسر المخرج بقدمك",
          "next": "node_ending_trapped"
        }
      ]
    },
    "node_hall": {
      "type": "decision",
      "text": "تصل للبهو وتجد لوحة الفرس الكبيرة معلقة بوجوم على الجدار المترب. إذا كنت قد قرأت المفكرة، يمكنك العثور على المفتاح السري، وإلا ستضطر لمحاولة دفع الباب الرئيسي الموصد بكل قوتك وهدر طاقتك.",
      "choices": [
        {
          "label": "تفتح اللوحة بالمفتاح السري",
          "next": "node_ending_escape",
          "requires_flag": "found_diary"
        },
        {
          "label": "تدفع الباب الرئيسي الموصد",
          "next": "node_ending_trapped"
        }
      ]
    },
    "node_ending_escape": {
      "type": "ending",
      "text": "تفتح اللوحة وتعثر على المفتاح السري لتخرج من القلعة مع بزوغ الفجر الأول. لقد نجوت بجسدك، لكن ذنبك القديم وظل صديقك المتروك سيبقيان في ذاكرتك للأبد يعذبانك دون فرصة للغفران. يمكنك المحاولة مجدداً واختيار مسارات أخرى لاستكشاف نهايات بديلة!",
      "is_ending": true,
      "choices": []
    },
    "node_ending_trapped": {
      "type": "ending",
      "text": "تفشل في فتح الباب أو كسر المخرج لتطبق عليك جدران القلعة بالظلال وتصبح سجيناً للأبد بجانب الهياكل العظمية. تموت وحيداً مع تذكر خيانتك القديمة. يمكنك المحاولة مجدداً واختيار مسارات أخرى لاستكشاف نهايات بديلة!",
      "is_ending": true,
      "choices": []
    }
  }
}
```

---

*Note: For detailed guidelines on story pacing, tone, and formatting, refer to [STORY_WRITING_GUIDE.md](file:///c:/Antigravity%20help/main%20bot/Main-bot-with-corrected-stories-main/stories_only_bot/docs/STORY_WRITING_GUIDE.md).*
