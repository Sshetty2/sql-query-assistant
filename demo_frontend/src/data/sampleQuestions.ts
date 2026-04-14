export interface QuestionCategory {
  label: string;
  icon: string;
  questions: string[];
}

export const SAMPLE_QUESTIONS: Record<string, QuestionCategory[]> = {
  demo_db_1: [
    {
      label: "Revenue & Sales",
      icon: "💰",
      questions: [
        "Show me the top 10 best-selling tracks by total revenue",
        "Total sales by country for the last year",
        "Show the total revenue broken down by genre and media type",
        "Average track price by genre for genres with more than 50 tracks",
      ],
    },
    {
      label: "Artists & Albums",
      icon: "🎵",
      questions: [
        "Which artists have the most albums?",
        "List all tracks along with their album names and composers",
        "Find the top 5 most expensive tracks",
        "Which genre has the most tracks?",
      ],
    },
    {
      label: "Playlists",
      icon: "📋",
      questions: [
        "Which tracks appear in the most playlists?",
        "List all playlists along with the number of tracks in each",
        "Find playlists that include tracks from the Rock genre",
      ],
    },
    {
      label: "Employees & Customers",
      icon: "👥",
      questions: [
        "List all employees and the customers they support",
        "List employees and the total sales they've generated from invoices",
        "Find customers who have purchased tracks from more than 3 genres",
        "Which customers are located in the United States?",
      ],
    },
  ],

  demo_db_2: [
    {
      label: "Orders & Revenue",
      icon: "📊",
      questions: [
        "Top 10 customers by total order value",
        "Monthly revenue trend by product category",
        "Revenue by employee and product category for the last quarter",
        "Average order value by country compared to the overall average",
      ],
    },
    {
      label: "Products & Inventory",
      icon: "📦",
      questions: [
        "Which products are running low on stock?",
        "Products that have never been ordered",
        "List all products with their category and supplier names",
        "Top 5 suppliers by total units sold across all their products",
      ],
    },
    {
      label: "Customers",
      icon: "🧑‍💼",
      questions: [
        "Customers who have ordered from every product category",
        "Show customer order history with product details",
        "List customers grouped by country with order counts",
      ],
    },
    {
      label: "Shipping & Delivery",
      icon: "🚚",
      questions: [
        "Show orders that shipped late with customer and shipper details",
        "Average shipping time by shipper company",
        "List orders with freight costs above the average",
      ],
    },
  ],

  demo_db_3: [
    {
      label: "Films & Actors",
      icon: "🎬",
      questions: [
        "Which actors have appeared in the most films?",
        "Actors who have appeared in both Action and Comedy films",
        "Films with above-average rental rates that have never been rented",
        "Show film inventory count by store and category",
      ],
    },
    {
      label: "Rentals & Payments",
      icon: "💳",
      questions: [
        "Top 10 customers by total rental payments",
        "Revenue per film category with average rental duration",
        "List overdue rentals with customer contact details",
        "Total rental revenue by month for the last year",
      ],
    },
    {
      label: "Customers",
      icon: "👤",
      questions: [
        "Customers who have rented from every film category",
        "List customers with their total rentals and payment amounts",
        "Show customer rental activity grouped by store",
      ],
    },
    {
      label: "Staff & Stores",
      icon: "🏪",
      questions: [
        "Staff member performance ranked by total revenue processed",
        "Compare inventory counts between stores",
        "Show staff assignments with their store details",
      ],
    },
  ],
};
