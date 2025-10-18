"""Enhanced metadata extraction supporting multiple AI generators via sd-parsers."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

from .tags import TagRecord, read_image_metadata

LOGGER = logging.getLogger(__name__)


@dataclass
class EnhancedImageMetadata:
    """Rich metadata extracted from AI-generated images."""

    # Basic image properties
    width: Optional[int] = None
    height: Optional[int] = None

    # AI generation metadata
    generator: Optional[str] = None
    model: Optional[str] = None
    source: Optional[str] = None

    # Prompts
    prompt: Optional[str] = None
    negative_prompt: Optional[str] = None

    # Generation parameters
    seed: Optional[str] = None
    steps: Optional[int] = None
    cfg_scale: Optional[float] = None
    sampler: Optional[str] = None
    scheduler: Optional[str] = None

    # Additional parameters
    denoising_strength: Optional[float] = None
    clip_skip: Optional[int] = None

    # Raw metadata for debugging/advanced use
    raw_sd_parsers: Optional[Dict[str, Any]] = None
    raw_chunks: Optional[Dict[str, str]] = None

    # Parsed tags from prompts
    tags: List[TagRecord] = None
    description: Optional[str] = None
    comment_meta: Optional[Dict[str, Any]] = None


def extract_enhanced_metadata(path: Path) -> EnhancedImageMetadata:
    """Extract comprehensive metadata from an image using sd-parsers with fallback."""
    metadata = EnhancedImageMetadata()

    # First try sd-parsers for comprehensive AI metadata
    try:
        _extract_with_sd_parsers(path, metadata)
    except Exception as exc:
        LOGGER.debug("sd-parsers extraction failed for %s: %s", path, exc)

    # Always try our existing metadata extraction as backup/supplement
    try:
        _extract_with_legacy_parser(path, metadata)
    except Exception as exc:
        LOGGER.debug("Legacy metadata extraction failed for %s: %s", path, exc)

    return metadata


def _extract_with_sd_parsers(path: Path, metadata: EnhancedImageMetadata) -> None:
    """Extract metadata using sd-parsers library."""
    try:
        from sd_parsers import ParserManager
        from sd_parsers.data import Generators
    except ImportError:
        LOGGER.debug("sd-parsers not available, skipping enhanced extraction")
        return

    parser = ParserManager()
    result = parser.parse(str(path))

    if not result:
        return

    # Store raw result for debugging
    try:
        metadata.raw_sd_parsers = {
            "generator": str(result.generator) if result.generator else None,
            "full_prompt": result.full_prompt,
            "full_negative_prompt": result.full_negative_prompt,
            "models": [m.name for m in result.models] if result.models else [],
            "samplers": [(s.name, dict(s.parameters)) for s in result.samplers]
            if result.samplers
            else [],
            "raw_parameters": result.raw_parameters,
        }
    except Exception as exc:
        LOGGER.debug("Failed to serialize sd-parsers raw data: %s", exc)

    # Extract generator
    if result.generator:
        generator_map = {
            Generators.NOVELAI: "NovelAI",
            Generators.AUTOMATIC1111: "Automatic1111",
            Generators.COMFYUI: "ComfyUI",
            Generators.INVOKEAI: "InvokeAI",
            Generators.FOOOCUS: "Fooocus",
        }
        metadata.generator = generator_map.get(result.generator, str(result.generator))

    # Extract prompts
    if result.full_prompt:
        metadata.prompt = result.full_prompt
    if result.full_negative_prompt:
        metadata.negative_prompt = result.full_negative_prompt

    # Extract model information
    if result.models and len(result.models) > 0:
        # Convert set to list to access first item
        models_list = list(result.models)
        metadata.model = models_list[0].name
        # For source, prefer the raw source field if available
        if hasattr(result, "raw_parameters") and result.raw_parameters:
            metadata.source = result.raw_parameters.get(
                "Source"
            ) or result.raw_parameters.get("source")
        if not metadata.source:
            metadata.source = models_list[0].name

    # Extract sampler and parameters from first sampler
    if result.samplers and len(result.samplers) > 0:
        sampler = result.samplers[0]
        metadata.sampler = sampler.name

        # Extract common parameters with more flexible key matching
        params = sampler.parameters or {}

        # Seed extraction
        for key in ["seed", "Seed"]:
            if key in params and params[key] is not None:
                metadata.seed = str(params[key])
                break

        # CFG Scale extraction
        for key in ["cfg_scale", "CFG scale", "cfg", "CFG"]:
            if key in params and params[key] is not None:
                try:
                    metadata.cfg_scale = float(params[key])
                    break
                except (ValueError, TypeError):
                    pass

        # Steps extraction
        for key in ["steps", "Steps", "step", "Step"]:
            if key in params and params[key] is not None:
                try:
                    metadata.steps = int(params[key])
                    break
                except (ValueError, TypeError):
                    pass

        # Scheduler extraction
        for key in ["scheduler", "Schedule type", "schedule"]:
            if key in params and params[key] is not None:
                metadata.scheduler = str(params[key])
                break

        # Denoising strength extraction
        for key in ["denoise", "Denoising strength", "denoising_strength"]:
            if key in params and params[key] is not None:
                try:
                    metadata.denoising_strength = float(params[key])
                    break
                except (ValueError, TypeError):
                    pass

        # Clip skip extraction
        for key in ["clip_skip", "Clip skip", "clipskip"]:
            if key in params and params[key] is not None:
                try:
                    metadata.clip_skip = int(params[key])
                    break
                except (ValueError, TypeError):
                    pass

    # Also check raw_parameters for additional extraction (NovelAI JSON comment)
    if hasattr(result, "raw_parameters") and result.raw_parameters:
        raw = result.raw_parameters

        # Extract from JSON comment (NovelAI style)
        if "Comment" in raw:
            try:
                import json

                comment_data = json.loads(raw["Comment"])

                # Extract steps from comment if not already set
                if not metadata.steps and "steps" in comment_data:
                    metadata.steps = int(comment_data["steps"])

                # NovelAI uses "scale" for CFG scale
                if not metadata.cfg_scale and "scale" in comment_data:
                    metadata.cfg_scale = float(comment_data["scale"])

                # Extract sampler name from comment if not already set
                if not metadata.sampler and "sampler" in comment_data:
                    metadata.sampler = str(comment_data["sampler"])

                # Extract scheduler from noise_schedule if available
                if not metadata.scheduler and "noise_schedule" in comment_data:
                    metadata.scheduler = str(comment_data["noise_schedule"])

            except (json.JSONDecodeError, KeyError, ValueError, TypeError):
                pass

        # Also try direct extraction from raw parameters for other generators
        if not metadata.steps and "Steps" in raw:
            try:
                metadata.steps = int(raw["Steps"])
            except (ValueError, TypeError):
                pass

        if not metadata.cfg_scale and "CFG scale" in raw:
            try:
                metadata.cfg_scale = float(raw["CFG scale"])
            except (ValueError, TypeError):
                pass


def _extract_with_legacy_parser(path: Path, metadata: EnhancedImageMetadata) -> None:
    """Extract metadata using existing LocalBooru PNG parser as fallback."""
    from .tags import collect_tags

    chunks = read_image_metadata(path)
    metadata.raw_chunks = chunks

    # Extract basic dimensions if not already set
    if not metadata.width and "Width" in chunks:
        try:
            metadata.width = int(chunks["Width"])
        except (ValueError, TypeError):
            pass

    if not metadata.height and "Height" in chunks:
        try:
            metadata.height = int(chunks["Height"])
        except (ValueError, TypeError):
            pass

    # Process tags and comments if sd-parsers didn't find prompts
    if not metadata.prompt or not metadata.tags:
        try:
            tags, description_text, comment_meta = collect_tags(chunks)

            if not metadata.tags:
                metadata.tags = tags
            if not metadata.description:
                metadata.description = description_text
            if not metadata.comment_meta:
                metadata.comment_meta = comment_meta

            # Extract parameters from comment_meta if not already set
            if comment_meta:
                if not metadata.seed and "seed" in comment_meta:
                    metadata.seed = str(comment_meta["seed"])

                if not metadata.model:
                    metadata.model = (
                        comment_meta.get("Source")
                        or comment_meta.get("source")
                        or chunks.get("Source")
                    )

                if not metadata.source:
                    metadata.source = (
                        chunks.get("Source")
                        or comment_meta.get("Source")
                        or comment_meta.get("source")
                    )

        except Exception as exc:
            LOGGER.debug("Failed to process legacy tags for %s: %s", path, exc)


def metadata_to_dict(metadata: EnhancedImageMetadata) -> Dict[str, Any]:
    """Convert metadata to dictionary for database storage."""
    return {
        "width": metadata.width,
        "height": metadata.height,
        "seed": metadata.seed,
        "model": metadata.model,
        "source": metadata.source,
        "description": metadata.description,
        "metadata_json": _serialize_extended_metadata(metadata),
    }


def _serialize_extended_metadata(metadata: EnhancedImageMetadata) -> Optional[str]:
    """Serialize extended metadata to JSON for database storage."""
    extended = {}

    # AI generation info
    if metadata.generator:
        extended["generator"] = metadata.generator
    if metadata.prompt:
        extended["prompt"] = metadata.prompt
    if metadata.negative_prompt:
        extended["negative_prompt"] = metadata.negative_prompt

    # Generation parameters
    if metadata.steps:
        extended["steps"] = metadata.steps
    if metadata.cfg_scale:
        extended["cfg_scale"] = metadata.cfg_scale
    if metadata.sampler:
        extended["sampler"] = metadata.sampler
    if metadata.scheduler:
        extended["scheduler"] = metadata.scheduler
    if metadata.denoising_strength:
        extended["denoising_strength"] = metadata.denoising_strength
    if metadata.clip_skip:
        extended["clip_skip"] = metadata.clip_skip

    # Include comment metadata from legacy parser
    if metadata.comment_meta:
        extended["comment_meta"] = metadata.comment_meta

    # Raw data for debugging (optional, can be large)
    if metadata.raw_sd_parsers:
        extended["raw_sd_parsers"] = metadata.raw_sd_parsers

    if not extended:
        return None

    try:
        return json.dumps(extended)
    except Exception as exc:
        LOGGER.warning("Failed to serialize extended metadata: %s", exc)
        return None


def get_prompt_tags_from_metadata(metadata: EnhancedImageMetadata) -> List[TagRecord]:
    """Extract tag records from prompts in metadata."""
    if metadata.tags:
        return metadata.tags

    # If we have prompts but no parsed tags, try to parse them
    if metadata.prompt:
        try:
            from .tags import parse_prompt_tags

            return parse_prompt_tags(metadata.prompt, "prompt")
        except Exception as exc:
            LOGGER.debug("Failed to parse prompt tags: %s", exc)

    return []
