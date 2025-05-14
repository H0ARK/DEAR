// Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT

import { toast } from "sonner";
import { create } from "zustand";

const REPOSITORIES_KEY = "deerflow.repositories";
const GITHUB_API_URL = "https://api.github.com";

export type Repository = {
  id: string;
  owner: string;
  name: string;
  fullName: string;
  description?: string;
  url: string;
  lastUsed: Date;
};

interface StoredRepository extends Omit<Repository, 'lastUsed'> {
  lastUsed: string;
}

interface GitHubRepo {
  full_name: string;
  name: string;
  owner: {
    login: string;
  };
  description: string | null;
  html_url: string;
}

export type RepositoryState = {
  repositories: Repository[];
  currentRepository: Repository | null;
  isLoading: boolean;
};

const DEFAULT_STATE: RepositoryState = {
  repositories: [],
  currentRepository: null,
  isLoading: false,
};

export const useRepositoryStore = create<RepositoryState>(() => ({
  ...DEFAULT_STATE,
}));

// Load repositories from localStorage
export function loadRepositories() {
  // Check if running in a browser environment
  if (typeof window !== 'undefined') {
    try {
      const storedData = localStorage.getItem(REPOSITORIES_KEY);
      if (storedData) {
        const parsed = JSON.parse(storedData);

        // Convert string dates back to Date objects
        const repositories = parsed.repositories.map((repo: StoredRepository) => ({
          ...repo,
          lastUsed: new Date(repo.lastUsed),
        }));

        useRepositoryStore.setState({
          repositories,
          currentRepository: parsed.currentRepository ? {
            ...parsed.currentRepository,
            lastUsed: new Date(parsed.currentRepository.lastUsed),
          } : null,
        });
      }
    } catch (error) {
      console.error("Failed to load repositories from localStorage:", error);
    }
  }
}

// Save repositories to localStorage
export function saveRepositories() {
  // Check if running in a browser environment
  if (typeof window !== 'undefined') {
    try {
      const { repositories, currentRepository } = useRepositoryStore.getState();
      localStorage.setItem(
        REPOSITORIES_KEY,
        JSON.stringify({ repositories, currentRepository })
      );
    } catch (error) {
      console.error("Failed to save repositories to localStorage:", error);
    }
  }
}

// Add a repository
export function addRepository(repository: Omit<Repository, "lastUsed">) {
  const newRepo = {
    ...repository,
    lastUsed: new Date(),
  };

  useRepositoryStore.setState((state) => {
    // Check if repository already exists
    const existingIndex = state.repositories.findIndex(
      (r) => r.fullName === repository.fullName
    );

    let updatedRepositories;
    if (existingIndex >= 0) {
      // Update existing repository
      updatedRepositories = [...state.repositories];
      updatedRepositories[existingIndex] = newRepo;
    } else {
      // Add new repository
      updatedRepositories = [...state.repositories, newRepo];
    }

    return {
      repositories: updatedRepositories,
      currentRepository: newRepo,
    };
  });

  saveRepositories();
}

// Set current repository
export function setCurrentRepository(repositoryId: string) {
  useRepositoryStore.setState((state) => {
    const repository = state.repositories.find((r) => r.id === repositoryId);
    if (!repository) return state;

    const updatedRepo = {
      ...repository,
      lastUsed: new Date(),
    };

    // Update the repository in the list
    const updatedRepositories = state.repositories.map((r) =>
      r.id === repositoryId ? updatedRepo : r
    );

    return {
      repositories: updatedRepositories,
      currentRepository: updatedRepo,
    };
  });

  saveRepositories();
}

// Remove a repository
export function removeRepository(repositoryId: string) {
  useRepositoryStore.setState((state) => {
    const updatedRepositories = state.repositories.filter(
      (r) => r.id !== repositoryId
    );

    // If the current repository is being removed, set to null or the first available
    const currentRepository =
      state.currentRepository?.id === repositoryId
        ? updatedRepositories.length > 0
          ? updatedRepositories[0]
          : null
        : state.currentRepository;

    return {
      repositories: updatedRepositories,
      currentRepository,
    };
  });

  saveRepositories();
}

// Set loading state
export function setRepositoriesLoading(isLoading: boolean) {
  useRepositoryStore.setState({ isLoading });
}

// Fetch repositories from GitHub
export async function fetchRepositoriesFromGitHub() {
  const token = localStorage.getItem('github_token');

  // If no token is available, don't try to fetch
  if (!token) {
    return;
  }

  setRepositoriesLoading(true);

  try {
    // Fetch user's repositories
    const response = await fetch(`${GITHUB_API_URL}/user/repos?sort=updated&per_page=10`, {
      headers: {
        'Authorization': `token ${token}`,
        'Accept': 'application/vnd.github.v3+json'
      }
    });

    if (!response.ok) {
      throw new Error(`GitHub API error: ${response.status}`);
    }

    const repos = await response.json();

    // Add each repository to the store
    repos.forEach((repo: GitHubRepo) => {
      addRepository({
        id: repo.full_name,
        owner: repo.owner.login,
        name: repo.name,
        fullName: repo.full_name,
        description: repo.description ?? undefined,
        url: repo.html_url
      });
    });

    // If we have repositories but no current repository is selected, select the first one
    const state = useRepositoryStore.getState();
    if (repos.length > 0 && !state.currentRepository) {
      setCurrentRepository(repos[0].full_name);
    }

    toast.success(`Loaded ${repos.length} repositories from GitHub`);
  } catch (error) {
    console.error('Error fetching repositories from GitHub:', error);
    toast.error('Failed to load repositories from GitHub');
  } finally {
    setRepositoriesLoading(false);
  }
}

// Initialize the store
loadRepositories();
